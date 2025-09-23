from __future__ import annotations
from typing import Any, Dict, Optional, List, Protocol
import os, requests, re

from src.core.agent import BaseAgent, AgentConfig, LLMAgent, load_prompt_text, SafeDict
from src.core.types import Message, Result


class LLMCallable(Protocol):
    def __call__(self, prompt: str, **kwargs) -> str: ...


# ---------- Parsers de Markdown ----------

# Captura a seção "### REWRITTEN QUERY" até o próximo heading "### ..."
_REWRITTEN = re.compile(
    r"^###\s*REWRITTEN\s+QUERY\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL
)
# Captura rationale em bullets (opcional)
_RATIONALE = re.compile(
    r"^###\s*RATIONALE\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL
)

def _extract_rewritten_query(md: str) -> str:
    m = _REWRITTEN.search(md or "")
    if not m:
        return ""
    # pega somente a primeira linha "útil"
    body = (m.group("body") or "").strip()
    # remove bullets se houver
    lines = [ln.strip(" -•\t") for ln in body.splitlines() if ln.strip()]
    return lines[0] if lines else ""

def _extract_rationale(md: str) -> List[str]:
    m = _RATIONALE.search(md or "")
    if not m:
        return []
    body = (m.group("body") or "").strip()
    bullets = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        s = s.lstrip("-• \t")
        if s:
            bullets.append(s)
    return bullets


# ---------- QueryRewriter Agent ----------

class QueryRewriterAgent(BaseAgent):
    """
    Reescreve a query usando LLMAgent para Ollama integration:
      - Usa LLMAgent com prompt_file para gerar Markdown
      - Faz parsing do Markdown e retorna:
          output = {"query": <rewritten>, "rationale": [...], "md": <raw>}
    Entrada esperada: Message.data com "question" OU "query".
    Opcional: "hints_md" (string) para enriquecer o prompt.
    """

    def __init__(self, config: AgentConfig, llm_fn: Optional[LLMCallable] = None):
        super().__init__(config)
        # Create an internal LLMAgent for Ollama communication
        self.llm_agent = LLMAgent(config, llm_fn)

    def _build_user_message(self, message: Message) -> Message:
        """Build the user message with context for the LLMAgent."""
        d = message.data if isinstance(message.data, dict) else {}
        question = d.get("question") or d.get("query") or str(message.data)
        hints_md = d.get("hints_md") or d.get("contexts_md") or ""
        
        # Build the user message data
        user_data = {
            "question": question,
            "hints_md": hints_md,
            "text": f"Please rewrite this query: {question}"
        }
        
        return Message(data=user_data, meta=message.meta)

    def run(self, message: Message) -> Result:
        # Build user message for LLMAgent
        user_message = self._build_user_message(message)
        
        # Use LLMAgent to get the response
        llm_result = self.llm_agent.run(user_message)
        
        if not llm_result.success:
            return Result.error(f"LLM call failed: {llm_result.output}")
        
        # Extract the markdown response
        md = llm_result.output.get("text", "")
        
        # Parse the markdown response
        rewritten = _extract_rewritten_query(md)
        rationale = _extract_rationale(md)

        if not rewritten:
            # se o LLM não respondeu no formato correto, devolve o original (com nota)
            original = ""
            if isinstance(message.data, dict):
                original = message.data.get("question") or message.data.get("query") or ""
            rewritten = original or ""
            disp = "✏️ Rewriter: fallback (format mismatch)"
        else:
            disp = f"✏️ Rewriter → {rewritten[:80]}"

        out = {"query": rewritten, "rationale": rationale, "md": md}
        return Result.ok(output=out, display_output=disp)
