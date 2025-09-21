from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional, List, Literal


ControlFlag = Dict[str, Any]
"""
Control flags understood by the WorkflowManager:
- goto: Optional[str]   -> jump to a specific next agent by name
- repeat: bool          -> re-execute the previous producer agent
- halt: bool            -> stop the workflow (successful or not)
"""

@dataclass
class Message:
    """Standard message that flows between agents."""
    data: Any
    meta: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return self.meta.get(key, default)

@dataclass
class Result:
    """Standard agent result."""
    success: bool
    output: Any = None
    display_output: Optional[str] = None
    control: ControlFlag = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    # Optional suggestion for downstream (e.g., prompt/model overrides)
    overrides: Dict[str, Any] = field(default_factory=dict)

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
            metrics=metrics or {}
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
            metrics=metrics or {}
        )

class WorkflowError(Exception):
    pass

class AgentExecutionError(Exception):
    pass
