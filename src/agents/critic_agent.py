from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable, Tuple
import json
import re

from src.core.agent import BaseAgent, AgentConfig, LLMCallable, load_prompt_text, SafeDict
from src.core.types import Message, Result


def _extract_text(payload: Any) -> str:
    """Extrai o texto a ser julgado (suporta dict/list/str)."""
    if isinstance(payload, list):
        return "\n\n".join(_extract_text(p) for p in payload)
    if isinstance(payload, dict):
        for k in ("text", "draft", "answer", "content", "output"):
            v = payload.get(k)
            if isinstance(v, str):
                return v
        return json.dumps(payload, ensure_ascii=False)[:8000]
    return str(payload)


class CriticAgent(BaseAgent):
    """
    Evaluator with .md prompt (in /prompts).
    Config (model_config):
    {
      "rubric": ["Clarity and structure", "Adherence to request", "Technical correctness"],
      "threshold": 7.5,        # 0..10
      "max_iters": 2,          # review limit
      "next_on_pass": "Done",  # (optional) goto when passing
      "prompt_file": "critic_agent.md"  # (optional) default = critic_agent.md
    }
    """
    def __init__(self, config: AgentConfig, llm_fn: LLMCallable):
        super().__init__(config)
        self.llm_fn = llm_fn

    def run(self, message: Message) -> Result:
        cfg = self._read_cfg()
        text = _extract_text(message.data)
        iteration = int(message.meta.get("iteration", 0))

        # Build prompt from .md file
        prompt_tmpl = load_prompt_text(cfg["prompt_file"])
        if not prompt_tmpl:
            raise FileNotFoundError(f"CriticAgent prompt not found: {cfg['prompt_file']}")

        rubric_text = "\n".join(f"- {criterion}" for criterion in cfg["rubric"])
        prompt = prompt_tmpl.format_map(SafeDict({
            "rubric_text": rubric_text,
            "text": text
        }))

        print(f"🔍 DEBUG: CriticAgent evaluating iteration {iteration}")
        print(f"📝 Text to evaluate: {text[:200]}...")
        
        llm_raw = self.llm_fn(prompt, **(self.config.model_config or {}))
        
        print(f"🤖 LLM Response: {llm_raw[:300]}...")

        # Parse markdown format instead of JSON
        parsed_result = self._parse_markdown_response(llm_raw, cfg["rubric"])
        
        if parsed_result is None:
            # If LLM doesn't follow format, treat as mild failure and request repeat
            feedback = {
                "score": 0.0,
                "passed": False,
                "iteration": iteration,
                "mode_used": "llm",
                "rubric": cfg["rubric"],
                "rubric_scores": {},
                "reasons": ["Invalid response format from evaluator"],
                "raw": llm_raw[:5000]
            }
            disp = f"🧪 Critic: invalid-format -> request repeat (iter={iteration})"
            print(f"❌ DEBUG: Invalid response format")
            if iteration >= cfg["max_iters"]:
                # no infinite loop
                return Result.ok(output=feedback, display_output=disp + " | max_iters", control={})
            return Result.ok(output=feedback, display_output=disp, control={"repeat": True})

        score = parsed_result["score"]
        rubric_scores = parsed_result["rubric_scores"]
        reasons = parsed_result["reasons"]

        passed = score >= cfg["threshold"]
        feedback = {
            "score": score,
            "passed": passed,
            "iteration": iteration,
            "mode_used": "llm",
            "rubric": cfg["rubric"],
            "rubric_scores": rubric_scores,
            "reasons": reasons
        }
        disp = f"🧪 Critic: score={score:.2f} pass={passed} iter={iteration}"
        
        print(f"✅ DEBUG: Evaluation complete - Score: {score}, Passed: {passed}")

        if passed:
            ctrl = {}
            if cfg["next_on_pass"]:
                ctrl["goto"] = cfg["next_on_pass"]
            return Result.ok(output=feedback, display_output=disp, control=ctrl)

        if iteration >= cfg["max_iters"]:
            return Result.ok(output=feedback, display_output=disp + " | max_iters", control={})

        return Result.ok(output=feedback, display_output=disp + " | request repeat", control={"repeat": True})

    # ----------------- helpers -----------------
    def _read_cfg(self) -> Dict[str, Any]:
        mc = self.config.model_config or {}
        rubric = mc.get("rubric") or ["Clarity and structure", "Adherence to request", "Technical correctness"]
        thr = float(mc.get("threshold", 7.5))
        max_iters = int(mc.get("max_iters", 2))
        next_on_pass = mc.get("next_on_pass")
        prompt_file = mc.get("prompt_file") or "critic_agent.md"
        return {
            "rubric": rubric,
            "threshold": thr,
            "max_iters": max_iters,
            "next_on_pass": next_on_pass,
            "prompt_file": prompt_file
        }

    def _parse_markdown_response(self, raw: str, rubric: List[str]) -> Optional[Dict[str, Any]]:
        """Parse markdown-formatted response instead of JSON."""
        try:
            # Look for overall score - handle both formats: "Score: 8.5" or "## Overall Score\n8.5"
            score_match = re.search(r'(?:Overall\s+Score|Score)[:：]?\s*(\d+(?:\.\d+)?)', raw, re.IGNORECASE)
            if not score_match:
                # Try multiline format: "## Overall Score" followed by number on next line(s)
                score_match = re.search(r'##\s*Overall\s+Score\s*\n+\s*(\d+(?:\.\d+)?)', raw, re.IGNORECASE)
            if not score_match:
                # Try simple number after "Score" heading
                score_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', raw)
            
            if not score_match:
                print(f"❌ DEBUG: Could not find score in response")
                print(f"📝 DEBUG: Response preview: {raw[:200]}...")
                return None
                
            score = float(score_match.group(1))
            print(f"✅ DEBUG: Found score: {score}")
            
            # Parse individual rubric scores
            rubric_scores = {}
            for criterion in rubric:
                # Look for patterns like "Clarity: 8", "- Clarity: 8/10", or multiline format
                pattern = rf'{re.escape(criterion)}[:：]?\s*(\d+(?:\.\d+)?)'
                match = re.search(pattern, raw, re.IGNORECASE)
                if match:
                    rubric_scores[criterion] = float(match.group(1))
                else:
                    # Default to overall score if individual not found
                    rubric_scores[criterion] = score
            
            # Extract reasons/feedback - handle both bullet points and multiline format
            reasons = []
            
            # Try multiline format first: "## Reasons" followed by bullet points
            reasons_section = re.search(r'##\s*Reasons?\s*\n+((?:\s*[-*•]\s*.+\n?)*)', raw, re.IGNORECASE | re.MULTILINE)
            if reasons_section:
                reason_text = reasons_section.group(1)
                bullets = re.findall(r'[-*•]\s*(.+)', reason_text)
                if bullets:
                    reasons = [bullet.strip() for bullet in bullets]
            
            # If no multiline format found, try other patterns
            if not reasons:
                reason_patterns = [
                    r'(?:Reasons?|Feedback)[:：]\s*\n((?:\s*[-*•]\s*.+\n?)+)',
                    r'((?:^\s*[-*•]\s*.+$)+)',
                    r'((?:^\s*\d+\.\s*.+$)+)'
                ]
                
                for pattern in reason_patterns:
                    match = re.search(pattern, raw, re.MULTILINE | re.IGNORECASE)
                    if match:
                        reason_text = match.group(1)
                        # Extract individual bullet points
                        bullets = re.findall(r'[-*•]\s*(.+)', reason_text)
                        if bullets:
                            reasons = [bullet.strip() for bullet in bullets]
                            break
                        # Extract numbered points
                        numbered = re.findall(r'\d+\.\s*(.+)', reason_text)
                        if numbered:
                            reasons = [point.strip() for point in numbered]
                            break
            
            if not reasons:
                # Fallback: extract any meaningful text as single reason
                lines = [line.strip() for line in raw.split('\n') if line.strip() and not re.match(r'^\d+(?:\.\d+)?', line.strip())]
                if lines:
                    reasons = ["Content evaluated"]
            
            return {
                "score": score,
                "rubric_scores": rubric_scores,
                "reasons": reasons
            }
            
        except Exception as e:
            print(f"❌ DEBUG: Error parsing markdown response: {e}")
            return None
