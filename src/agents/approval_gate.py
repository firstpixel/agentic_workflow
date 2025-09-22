from __future__ import annotations
import uuid
from typing import Any, Dict, Optional, List

from src.core.agent import BaseAgent, AgentConfig, LLMAgent, load_prompt_text, SafeDict
from src.core.types import Message, Result


class ApprovalGateAgent(BaseAgent):
    """
    Human-in-the-loop gate com duas fases:

    Fase 1 (request): Gera um resumo em Markdown (via LLMAgent + prompt .md) e HALT o fluxo.
      - input: { "text" | "content" | ... } (qualquer payload com texto)
      - output: { "status":"PENDING", "approval_id": "...", "summary_md": "<md>" }
      - control: {"halt": True}

    Fase 2 (decision): Recebe a decisão humana e encaminha.
      - input: { "approval_id": "...", "human_decision": "APPROVE"|"REJECT", "human_comment": "..."? }
      - output: { "status":"APPROVED"|"REJECTED", ... }
      - control: {"goto": next_on_approve | next_on_reject} ou {"halt": True} se rejeitar e não houver rota.

    model_config:
    {
      "summary_prompt_file": "approval_request.md",  # prompt para gerar resumo
      "next_on_approve": "NextNodeName",             # obrigatório para avançar
      "next_on_reject": "ReworkNodeName",            # opcional
      "model": "llama3",
      "options": {"temperature": 0.1}
    }
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        # Store pending requests with their original content
        self._pending_requests: Dict[str, str] = {}

    # --------- helpers -----------
    def _extract_text(self, data: Any) -> str:
        if isinstance(data, dict):
            for k in ("text","content","prompt","input","query","message"):
                v = data.get(k)
                if isinstance(v, str):
                    return v
        return str(data)

    def _summarize_for_human(self, content_md: str) -> str:
        mc = self.config.model_config or {}
        prompt_file = mc.get("summary_prompt_file") or "approval_request.md"

        # Reusa LLMAgent com prompt .md (sem mock)
        llm_cfg = AgentConfig(
            name=f"{self.config.name}::Summarizer",
            prompt_file=prompt_file,
            model_config=mc
        )
        summarizer = LLMAgent(llm_cfg)
        res = summarizer.execute(Message(data={"content_md": content_md}))
        if res.success and isinstance(res.output, dict):
            return res.output.get("text", "") or ""
        return ""

    # --------- main --------------
    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        nxt_ok = mc.get("next_on_approve")
        nxt_no = mc.get("next_on_reject")

        d = message.data if isinstance(message.data, dict) else {}
        human_decision = d.get("human_decision")

        # ---- Fase 2: decisão humana ----
        if isinstance(human_decision, str):
            dec = human_decision.strip().upper()
            comment = d.get("human_comment","")
            approval_id = d.get("approval_id", "")
            
            # Retrieve original content
            original_content = self._pending_requests.get(approval_id, "")
            
            if dec == "APPROVE":
                disp = "🧑‍⚖️ Approval: APPROVED"
                ctrl = {}
                if nxt_ok:
                    ctrl["goto"] = nxt_ok
                
                # Combine original content with human feedback
                enhanced_content = original_content
                if comment:
                    enhanced_content += f"\n\nHuman feedback: {comment}"
                
                # Clean up stored request
                if approval_id in self._pending_requests:
                    del self._pending_requests[approval_id]
                
                return Result.ok(
                    output={
                        "status":"APPROVED",
                        "comment":comment,
                        "text": enhanced_content,
                        "message_text": enhanced_content  # For prompt compatibility
                    },
                    display_output=disp,
                    control=ctrl
                )
            else:
                disp = "🧑‍⚖️ Approval: REJECTED"
                ctrl = {}
                if nxt_no:
                    ctrl["goto"] = nxt_no
                else:
                    ctrl["halt"] = True
                
                # Clean up stored request
                if approval_id in self._pending_requests:
                    del self._pending_requests[approval_id]
                    
                return Result.ok(
                    output={"status":"REJECTED","comment":comment},
                    display_output=disp,
                    control=ctrl
                )

        # ---- Fase 1: gerar resumo e pausar ----
        content_md = self._extract_text(d or message.data)
        summary_md = self._summarize_for_human(content_md)
        approval_id = str(uuid.uuid4())
        
        # Store the original content for later retrieval
        self._pending_requests[approval_id] = content_md

        disp = "🧑‍⚖️ Approval: PENDING (halt)"
        out = {
            "status": "PENDING",
            "approval_id": approval_id,
            "summary_md": summary_md
        }
        return Result.ok(output=out, display_output=disp, control={"halt": True})
