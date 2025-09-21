from __future__ import annotations
from typing import Any, Dict, List

from src.core.agent import BaseAgent, AgentConfig
from src.core.types import Message, Result


def _extract_textish(x: Any) -> str:
    """
    Extrai representação textual razoável de cada item vindo dos ramos.
    Procura por chaves comuns; caso contrário, str(x).
    """
    if isinstance(x, dict):
        for k in ("text", "content", "answer", "output", "echo"):
            v = x.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return str(x)
    return str(x)


class JoinAgent(BaseAgent):
    """
    Agrega resultados de múltiplos ramos. Não usa LLM nem prompt.
    Entrada esperada: Message.data pode ser uma LISTA (quando múltiplas entradas chegaram).
    Saída: {"text": <concatenação legível dos resultados>}
    """
    def run(self, message: Message) -> Result:
        data = message.data
        if not isinstance(data, list):
            # fluxo degenerado (chegou um único item). Ainda assim, retorne algo útil.
            combined = _extract_textish(data)
        else:
            parts = []
            for i, item in enumerate(data, start=1):
                parts.append(f"[Branch {i}]\n{_extract_textish(item)}")
            combined = "\n\n".join(parts)

        disp = f"🔗 Join ({'multi' if isinstance(message.data, list) else 'single'})"
        return Result.ok(output={"text": combined}, display_output=disp)
