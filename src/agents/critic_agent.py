import re
import json
from typing import Dict, Any
from src.core.agent import BaseAgent, AgentConfig, LLMAgent
from src.core.types import Message, Result

_MD_DECISION = re.compile(r"##\s*DECISION\s*[:\n]\s*([^\n]*)", re.IGNORECASE)
_MD_SCORE = re.compile(r"##\s*SCORE\s*[:\n]\s*([0-9.]+)", re.IGNORECASE)

def _extract_text(payload):
    if isinstance(payload, dict):
        for k in ("text", "prompt", "input", "query", "content"):
            if isinstance(payload.get(k), str):
                return payload[k]
    return str(payload)

def _parse_markdown(md: str) -> Dict[str,Any]:
    decision="REVISE"
    m=_MD_DECISION.search(md or "")
    if m: decision=m.group(1).strip().upper()
    s=_MD_SCORE.search(md or "")
    score=float(s.group(1)) if s else 0.0
    return {"decision": decision, "score": score, "raw": md}

class CriticAgent(BaseAgent):
    """
    Evaluates content using LLMAgent with Markdown output. If DECISION=PASS, continues; otherwise requests repeat.
    Uses internal LLMAgent with system prompt from config.prompt_file (default: critic_agent.md)
    
    model_config:
      rubric: [...]
      threshold: float (0..10)
      max_iters: int
      next_on_pass: str (optional)
      model: str (for LLMAgent)
    """
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        # Create internal LLMAgent - it will load the system prompt automatically
        self.llm_agent = LLMAgent(config)

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        rubric = mc.get("rubric") or ["Clearness","Adherence","Correctness"]
        threshold=float(mc.get("threshold",7.5))
        max_iters=int(mc.get("max_iters",2))
        next_on_pass=mc.get("next_on_pass")

        text=_extract_text(message.data)
        iteration=int(message.meta.get("iteration",0))

        # Build user prompt with context for the system prompt template
        user_prompt = f"""Text to evaluate: {text}

Rubric: {json.dumps(rubric, ensure_ascii=False)}
Current iteration: {iteration}

Please evaluate this content according to the rubric and provide your assessment."""

        # Use LLMAgent with new interface
        llm_message = Message(data={"user_prompt": user_prompt}, meta=message.meta)
        llm_result = self.llm_agent.run(llm_message)
        
        if not llm_result.success:
            return Result.error(f"LLM evaluation failed: {llm_result.output}")
            
        md = llm_result.output.get("text", "")
        parsed=_parse_markdown(md)
        passed = parsed["decision"]=="PASS" and parsed["score"]>=threshold

        # Prepare output with score and rubric included
        output_data = message.data.copy() if isinstance(message.data, dict) else {"text": message.data}
        output_data["score"] = parsed["score"]
        output_data["decision"] = parsed["decision"]
        output_data["rubric"] = rubric  # Include rubric for testing

        if passed or iteration >= max_iters:
            if passed and next_on_pass:
                return Result.ok(output=output_data, 
                               display_output=f"✅ Critic: PASS score={parsed['score']:.1f}",
                               control={"goto": next_on_pass})
            else:
                return Result.ok(output=output_data, 
                               display_output=f"✅ Critic: PASS score={parsed['score']:.1f}")
        else:
            return Result.ok(output=output_data, 
                           display_output=f"❌ Critic: {parsed['decision']} score={parsed['score']:.1f}",
                           control={"repeat": True})
