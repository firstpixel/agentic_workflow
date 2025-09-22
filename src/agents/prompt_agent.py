# agents/prompt_agent.py
from __future__ import annotations
from typing import Any, Dict, List
import re

from src.core.agent import BaseAgent, AgentConfig, LLMAgent, load_prompt_text, SafeDict
from src.core.types import Message, Result

# -------- Parsers de Markdown --------
_TARGET_PROMPTS = re.compile(
    r"^###\s*TARGET\s+PROMPTS\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL
)
_PLAN = re.compile(
    r"^###\s*PLAN\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL
)

def _parse_target_prompts(md: str) -> Dict[str, str]:
    """
    Lê linhas tipo:
      - Writer: writer_bullets.md
    Retorna: {'Writer': 'writer_bullets.md', ...}
    """
    out: Dict[str, str] = {}
    m = _TARGET_PROMPTS.search(md or "")
    if not m:
        return out
    body = (m.group("body") or "").strip()
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        s = s.lstrip("-• \t")
        if ":" in s:
            k, v = s.split(":", 1)
            out[k.strip()] = v.strip()
        else:
            parts = s.split()
            if len(parts) >= 2:
                out[parts[0].strip()] = parts[1].strip()
    return out

def _parse_plan(md: str) -> str:
    m = _PLAN.search(md or "")
    return (m.group("body").strip() if m else "")


class PromptAgent(BaseAgent):
    """
    Prompt/Plan Handoff:
      - Decide 'prompt_file' por agente-alvo (via Markdown)
      - Gera 'plan_md' para ser consumido pelo próximo nó

    model_config:
    {
      "prompt_file": "prompt_agent.md",    # REQUIRED
      "model": "...", "options": {...},
      "default_targets": {"Writer": "writer_bullets.md"}  # fallback
    }

    Saída:
      overrides["for"] = { "<Agent>": {"prompt_file": "<file.md>"} }
      output[<Agent>]   = { "plan_md": "<markdown>" }   # payload por ramo
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
            raise ValueError("PromptAgent requer model_config['prompt_file'] (ex.: 'prompt_agent.md').")

        # Usa seu LLMAgent (Ollama) para gerar a decisão
        llm = LLMAgent(AgentConfig(
            name=f"{self.config.name}::LLM",
            prompt_file=prompt_file,
            model_config=mc
        ))
        text = self._extract_text(message.data)
        md = llm.execute(Message(data={"text": text})).output.get("text","")

        targets = _parse_target_prompts(md)
        if not targets:
            targets = dict(mc.get("default_targets") or {})

        plan_md = _parse_plan(md)

        # overrides direcionados (Task 9)
        targeted = {agent_name: {"prompt_file": file_name} for agent_name, file_name in targets.items()}

        # payload por ramo com o plano
        per_branch_payload: Dict[str, Any] = {}
        for agent_name in targets.keys():
            per_branch_payload[agent_name] = {"plan_md": plan_md} if plan_md else {}

        disp = f"🧭 PromptAgent -> targets={targets} plan={'yes' if plan_md else 'no'}"
        return Result.ok(
            output={**per_branch_payload},           # per-branch payload
            display_output=disp,
            overrides={"for": targeted} if targeted else {}
        )
