from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


ControlFlag = Dict[str, Any]
"""
Entendido pelo WorkflowManager:
- goto: Optional[str]   -> pula para um nó específico
- repeat: bool          -> refaz o produtor anterior (loop de reflexão)
- halt: bool            -> encerra o fluxo
"""

@dataclass
class Message:
    """Envelope padrão que circula no fluxo."""
    data: Any
    meta: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return self.meta.get(key, default)

@dataclass
class Result:
    """Saída padrão de qualquer agente."""
    success: bool
    output: Any = None
    display_output: Optional[str] = None
    control: ControlFlag = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    overrides: Dict[str, Any] = field(default_factory=dict)  # prompts/model_config futuros

    @staticmethod
    def ok(output: Any = None, display_output: Optional[str] = None,
           control: Optional[ControlFlag] = None, overrides: Optional[Dict[str, Any]] = None,
           metrics: Optional[Dict[str, Any]] = None) -> "Result":
        return Result(
            success=True,
            output=output,
            display_output=display_output,
            control=control or {},
            overrides=overrides or {},
            metrics=metrics or {},
        )

    @staticmethod
    def fail(output: Any = None, display_output: Optional[str] = None,
             control: Optional[ControlFlag] = None, overrides: Optional[Dict[str, Any]] = None,
             metrics: Optional[Dict[str, Any]] = None) -> "Result":
        return Result(
            success=False,
            output=output,
            display_output=display_output,
            control=control or {},
            overrides=overrides or {},
            metrics=metrics or {},
        )


class WorkflowError(Exception):
    pass


class AgentExecutionError(Exception):
    pass
