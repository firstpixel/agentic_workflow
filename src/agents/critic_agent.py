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
    Avaliador com prompt .md (em /prompts).
    Config (model_config):
    {
      "rubric": ["Clareza e estrutura", "Aderência ao pedido", "Corretude técnica"],
      "threshold": 7.5,        # 0..10
      "max_iters": 2,          # limite de revisões
      "next_on_pass": "Done",  # (opcional) goto quando passar
      "prompt_file": "critic_agent.md"  # (opcional) default = critic_agent.md
    }
    """
    def __init__(self, config: AgentConfig, llm_fn: LLMCallable):
        super().__init__(config)
        self.llm_fn = llm_fn

    def run(self, message: Message) -> Result:
        cfg = self._read_cfg()
        text = _extract_text(message.data)
        iteration = int(message.meta.get("iteration", 0))

        # Monta prompt a partir do arquivo .md
        prompt_tmpl = load_prompt_text(cfg["prompt_file"])
        if not prompt_tmpl:
            raise FileNotFoundError(f"CriticAgent prompt not found: {cfg['prompt_file']}")

        prompt = prompt_tmpl.format_map(SafeDict({
            "rubric_json": json.dumps(cfg["rubric"], ensure_ascii=False),
            "text": text
        }))

        llm_raw = self.llm_fn(prompt, **(self.config.model_config or {}))

        # Parse JSON estrito, com fallback para bloco {...}
        obj = self._parse_json(llm_raw)
        if obj is None or "score" not in obj or "rubric_scores" not in obj:
            # Se o LLM não respeitar o formato, trata como reprovação leve e pede repeat
            feedback = {
                "score": 0.0,
                "passed": False,
                "iteration": iteration,
                "mode_used": "llm",
                "rubric": cfg["rubric"],
                "rubric_scores": {},
                "reasons": ["Invalid JSON from evaluator"],
                "raw": llm_raw[:5000]
            }
            disp = f"🧪 Critic: invalid-json -> request repeat (iter={iteration})"
            if iteration >= cfg["max_iters"]:
                # sem loop infinito
                return Result.ok(output=feedback, display_output=disp + " | max_iters", control={})
            return Result.ok(output=feedback, display_output=disp, control={"repeat": True})

        score = float(obj.get("score", 0.0))
        rubric_scores = obj.get("rubric_scores", {}) or {}
        reasons = obj.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = [str(reasons)]

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
        rubric = mc.get("rubric") or ["Clareza e estrutura", "Aderência ao pedido", "Corretude técnica"]
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

    def _parse_json(self, raw: str) -> Optional[Dict[str, Any]]:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except Exception:
            pass
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
