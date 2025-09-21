from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.agent import BaseAgent, AgentConfig
from src.core.types import Message, Result


class FanOutAgent(BaseAgent):
    """
    Produz payloads por ramo. Não usa LLM nem prompt.
    Config (model_config):
    {
      "branches": ["TechWriter", "BizWriter"]  # nomes dos nós downstream no grafo
      # opcionalmente, você pode no futuro permitir payloads específicos por ramo
    }

    Saída: dict { "<next_node>": <payload para aquele nó> }
    Se nenhum payload específico for informado, replica a entrada para todos os ramos.
    """
    def run(self, message: Message) -> Result:
        cfg = self.config.model_config or {}
        branches: List[str] = cfg.get("branches") or []
        if not branches:
            raise ValueError("FanOutAgent: defina model_config['branches'] com a lista de ramos")

        # Por padrão, replica a mesma entrada para cada ramo.
        out: Dict[str, Any] = {b: message.data for b in branches}
        disp = f"↗️ FanOut -> {', '.join(branches)}"
        return Result.ok(output=out, display_output=disp)
