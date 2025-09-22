from __future__ import annotations
from typing import Any, Dict, List
import re

from agent import BaseAgent, AgentConfig, LLMAgent, load_prompt_text, SafeDict
from types import Message, Result

# Markdown sections
_DECISION = re.compile(r"^###\s*DECISION\s*\n([^\n]+)", re.IGNORECASE | re.MULTILINE)
_TARGETS  = re.compile(r"^###\s*TARGETS\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)

def _parse_decision(md: str) -> str:
    m = _DECISION.search(md or "")
    return (m.group(1).strip().upper() if m else "").replace("-", "_")

def _parse_targets(md: str) -> Dict[str, str]:
    out: Dict[str,str] = {}
    m = _TARGETS.search(md or "")
    if not m: return out
    body = (m.group("body") or "")
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        s = s.lstrip("-• \t")
        # Accept formats: "Writer: SIMPLE" or "Writer SIMPLE"
        if ":" in s:
            k, v = s.split(":", 1)
            out[k.strip()] = v.strip().upper().replace("-", "_")
        else:
            parts = s.split()
            if len(parts) >= 2:
                out[parts[0].strip()] = parts[1].strip().upper().replace("-", "_")
    return out

class ModelRouterAgent(BaseAgent):
    """
    Resource-Aware router that sets model/prompt overrides for downstream agents.

    model_config:
    {
      "prompt_file": "model_router.md",     # REQUIRED
      "classes": {
        "SIMPLE":   {"model": "llama3", "options": {"temperature": 0.1}},
        "STANDARD": {"model": "llama3", "options": {"temperature": 0.3}},
        "COMPLEX":  {"model": "llama3", "options": {"temperature": 0.6}}
      },
      "targets": ["Writer", "Critic"]       # default targets if ### TARGETS is absent
    }

    Output:
      - res.overrides["for"] = { "<AgentName>": {"model_config": {...}} }
    """
    def __init__(self, config: AgentConfig):
        super().__init__(config)

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, dict):
            for k in ("text","prompt","input","query","content","message"):
                v = data.get(k)
                if isinstance(v, str):
                    return v
        return str(data)

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        prompt_file = mc.get("prompt_file")
        if not prompt_file:
            raise ValueError("ModelRouterAgent requires model_config['prompt_file'] (e.g., 'model_router.md').")

        classes = mc.get("classes") or {}
        default_targets: List[str] = mc.get("targets") or []

        # Build the router prompt using LLMAgent (so we reuse your Ollama integration)
        router_llm = LLMAgent(AgentConfig(
            name=f"{self.config.name}::LLM",
            prompt_file=prompt_file,
            model_config=mc  # model/options/timeout are reused
        ))

        text = self._extract_text(message.data)
        md = router_llm.execute(Message(data={"text": text})).output.get("text","")

        decision = _parse_decision(md) or "STANDARD"
        targets_map = _parse_targets(md)
        if not targets_map and default_targets:
            # apply single decision to default_targets
            targets_map = {t: decision for t in default_targets}

        # Build targeted overrides for WorkflowManager
        target_overrides: Dict[str, Dict[str, Any]] = {}
        for tgt, cls in targets_map.items():
            cfg = classes.get(cls)
            if not isinstance(cfg, dict):
                # fall back to decision class
                cfg = classes.get(decision, {})
            if cfg:
                target_overrides[tgt] = {"model_config": cfg}

        disp = f"🧭 Router: decision={decision} targets={list(targets_map.keys())}"
        out = {"decision": decision, "targets": targets_map, "md": md}

        return Result.ok(
            output=out,
            display_output=disp,
            overrides={"for": target_overrides} if target_overrides else {}
        )
