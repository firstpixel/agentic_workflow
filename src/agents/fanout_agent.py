from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.agent import BaseAgent, AgentConfig
from src.core.types import Message, Result


def _convert_to_user_prompt_format(data: Any) -> Any:
    """Convert message data to user_prompt format for LLMAgent compatibility."""
    if isinstance(data, dict):
        # If already has user_prompt, return as-is
        if "user_prompt" in data:
            return data
        # Convert text/prompt/query to user_prompt
        for key in ("text", "prompt", "query", "input", "content"):
            if key in data and isinstance(data[key], str):
                new_data = dict(data)
                new_data["user_prompt"] = data[key]
                return new_data
    # If it's a string, wrap it in user_prompt
    elif isinstance(data, str):
        return {"user_prompt": data}
    
    # Fallback: wrap in user_prompt as string
    return {"user_prompt": str(data)}


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
    Automatically converts message format to user_prompt format for LLMAgent compatibility.
    """
    def run(self, message: Message) -> Result:
        cfg = self.config.model_config or {}
        branches: List[str] = cfg.get("branches") or []
        if not branches:
            raise ValueError("FanOutAgent: defina model_config['branches'] com a lista de ramos")

        # Convert message data to user_prompt format for LLMAgent compatibility
        converted_data = _convert_to_user_prompt_format(message.data)
        
        # Por padrão, replica a mesma entrada para cada ramo.
        out: Dict[str, Any] = {b: converted_data for b in branches}
        disp = f"↗️ FanOut -> {', '.join(branches)}"
        return Result.ok(output=out, display_output=disp)
