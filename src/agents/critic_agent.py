from __future__ import annotations
from typing import Any, Dict, List, Optional, Callable
import json, re
from src.core.agent import BaseAgent, AgentConfig, LLMCallable, load_prompt_text, SafeDict
from src.core.types import Message, Result

def _extract_text(payload: Any) -> str:
    if isinstance(payload, list):
        return "\n\n".join(_extract_text(p) for p in payload)
    if isinstance(payload, dict):
        for k in ("text","draft","answer","content","output"):
            v = payload.get(k)
            if isinstance(v,str): return v
        return json.dumps(payload, ensure_ascii=False)[:8000]
    return str(payload)

_MD_DECISION=re.compile(r"^###\s*DECISION\s*\n([^\n]+)", re.IGNORECASE|re.MULTILINE)
_MD_SCORE   =re.compile(r"^###\s*SCORE\s*\n([0-9]+(\.[0-9]+)?)", re.IGNORECASE|re.MULTILINE)

def _parse_markdown(md: str) -> Dict[str,Any]:
    decision="REVISE"
    m=_MD_DECISION.search(md or "")
    if m: decision=m.group(1).strip().upper()
    s=_MD_SCORE.search(md or "")
    score=float(s.group(1)) if s else 0.0
    return {"decision": decision, "score": score, "raw": md}

class CriticAgent(BaseAgent):
    """
    Avalia em Markdown (sem JSON). Se DECISION=PASS, segue; caso contrário, pede repeat.
    model_config:
      rubric: [...]
      threshold: float (0..10)
      max_iters: int
      next_on_pass: str (opcional)
      prompt_file: str (default critic_agent.md)
    """
    def __init__(self, config: AgentConfig, llm_fn: LLMCallable):
        super().__init__(config)
        self.llm_fn = llm_fn

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        rubric = mc.get("rubric") or ["Clearness","Adherence","Correctness"]
        threshold=float(mc.get("threshold",7.5))
        max_iters=int(mc.get("max_iters",2))
        next_on_pass=mc.get("next_on_pass")
        prompt_file=mc.get("prompt_file") or "critic_agent.md"

        text=_extract_text(message.data)
        iteration=int(message.meta.get("iteration",0))

        tmpl=load_prompt_text(prompt_file)
        if not tmpl: raise FileNotFoundError(f"Missing prompt file: {prompt_file}")
        prompt=tmpl.format_map(SafeDict({"rubric_json": json.dumps(rubric,ensure_ascii=False),"text":text}))

        md=self.llm_fn(prompt, **mc)
        parsed=_parse_markdown(md)
        passed = parsed["decision"]=="PASS" and parsed["score"]>=threshold

        disp=f"🧪 Critic(decision={parsed['decision']}, score={parsed['score']:.2f}, iter={iteration})"
        feedback={"decision":parsed["decision"],"score":parsed["score"],"iteration":iteration,"rubric":rubric}

        if passed:
            ctrl={}
            if next_on_pass: ctrl["goto"]=next_on_pass
            return Result.ok(output=feedback, display_output=disp, control=ctrl)

        if iteration>=max_iters:
            return Result.ok(output=feedback, display_output=disp+" | max_iters", control={})
        return Result.ok(output=feedback, display_output=disp+" | request repeat", control={"repeat":True})
