from __future__ import annotations
from typing import Any, Dict, Optional

from src.core.agent import BaseAgent, AgentConfig, LLMAgent, load_prompt_text, SafeDict
from src.core.types import Message, Result
from src.guardrails.guardrails import redact_pii, parse_moderation_md


class GuardrailsAgent(BaseAgent):
    """
    Aplica redaction de PII (determinístico) e moderação por LLM (Markdown).

    model_config:
    {
      "pii_redact": true,
      "moderation_mode": "hybrid",           # "deterministic" | "llm" | "hybrid"
      "moderation_prompt_file": "moderation.md",
      "model": "llama3",
      "options": {"temperature": 0.0}
    }

    Saída:
      - output = { "decision": ..., "text": <sanitized>, "pii": {...}, "reasons": [...], "md": <raw> }
      - control.halt = True se decision == "BLOCK"
      - Caso decision == "REDACT", o texto redigido segue adiante
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
        pii_on   = bool(mc.get("pii_redact", True))
        mode     = (mc.get("moderation_mode") or "hybrid").lower()
        prompt_f = mc.get("moderation_prompt_file") or "moderation.md"

        original_text = self._extract_text(message.data)

        # 1) PII redaction determinístico
        red_text, counts, pii_md_list = redact_pii(original_text) if pii_on else (original_text, {"email":0,"phone":0,"card":0}, [])
        pii_md = "\n".join(pii_md_list) if pii_md_list else "(none)"
        decision = "ALLOW"
        reasons = []
        mod_md = ""

        # 2) Moderação por LLM (Markdown) – via LLMAgent
        use_llm = (mode in ("llm","hybrid"))
        if use_llm:
            # constrói um LLMAgent interno só para a moderação
            llm_cfg = AgentConfig(
                name=f"{self.config.name}::Moderator",
                prompt_file=prompt_f,
                model_config={k:v for k,v in mc.items()}  # inclui model/options/timeout
            )
            moderator = LLMAgent(llm_cfg)  # usa Ollama por padrão
            prompt_input = {"text": original_text, "pii_md": pii_md}
            md_res = moderator.execute(Message(data=prompt_input))
            mod_md = (md_res.output or {}).get("text","") if md_res.success else ""
            parsed = parse_moderation_md(mod_md)
            decision = parsed["decision"]
            reasons  = parsed["reasons"]

        # 3) Modo determinístico puro (ou fallback)
        if mode == "deterministic" or (mode == "hybrid" and not use_llm):
            # se encontrou PII -> REDACT, senão ALLOW
            decision = "REDACT" if sum(counts.values()) > 0 else "ALLOW"

        # 4) Control + saída
        control = {}
        if decision == "BLOCK":
            control["halt"] = True

        sanitized = red_text if decision in ("ALLOW","REDACT") else ""
        disp = f"🛡️ Guardrails(decision={decision}, pii={counts})"

        out = {
            "decision": decision,
            "text": sanitized,
            "pii": counts,
            "reasons": reasons,
            "md": mod_md
        }
        return Result.ok(output=out, display_output=disp, control=control)
