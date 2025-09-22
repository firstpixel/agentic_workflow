"""
Model Selector Agent for routing and applying model overrides.
"""
from typing import Dict, Any, Optional
import re
import os

from src.core.agent import LLMAgent, AgentConfig, load_prompt_text, SafeDict
from src.core.types import Result, Message

# Compiled regex pattern for better performance and accuracy
_DECISION = re.compile(r"###\s*DECISION\s*\n(.*?)(?=\n###|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)


class ModelSelectorAgent(LLMAgent):
    """
    Agent that selects and applies model configurations based on routing decisions.
    """
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.classes = config.model_config.get("classes", {})
        self.targets = config.model_config.get("targets", [])
    
    def run(self, message: Message) -> Result:
        """
        Run the model selector to determine routing and apply overrides.
        """
        try:
            # Validate required configuration
            if not self.config.prompt_file:
                raise ValueError("ModelSelectorAgent requires prompt_file in AgentConfig")
            
            # Get the LLM routing decision
            result = super().run(message)
            
            if not result.success:
                return result
            
            # Extract text from the result output
            output_text = ""
            if isinstance(result.output, dict) and "text" in result.output:
                output_text = result.output["text"]
            elif isinstance(result.output, str):
                output_text = result.output
            else:
                output_text = str(result.output)
            
            # Parse only the decision from LLM output  
            decision = self._parse_decision(output_text)
            
            # Apply the decision to all configured targets (the selector doesn't decide targets)
            target_overrides: Dict[str, Dict[str, Any]] = {}
            if self.targets:
                cfg = self.classes.get(decision, {})
                if cfg:
                    for target in self.targets:
                        target_overrides[target] = {"model_config": cfg}
            
            # More informative display output
            display_msg = f"🔀 Selector: decision={decision} targets={self.targets}"
            
            # Return result with routing information and overrides
            routing_info = {
                "decision": decision,
                "model_config": cfg if cfg else {},  # Include the config for debugging
                "downstream_agents": list(target_overrides.keys()),
                "md": decision  # Simplified debug output
            }
            
            return Result(
                success=True,
                output=routing_info,
                display_output=display_msg,
                overrides={"for": target_overrides} if target_overrides else None
            )
            
        except Exception as e:
            return Result(success=False, output=str(e))
    
    def _build_prompt(self, message: Message) -> str:
        """Override to add debug info."""
        ctx = {
            "root": message.meta.get("root", ""),
            "previous": "",
            "critic_feedback": message.meta.get("critic_feedback", ""),
            "iteration": message.meta.get("iteration", 0),
            "message_text": self._extract_message_text(message),
        }
        if isinstance(message.data, dict) and "previous" in message.data and "input" in message.data:
            ctx["root"] = message.data.get("input", ctx["root"])
            ctx["previous"] = message.data.get("previous", "")

        # Include all keys from message.data in the context for template formatting
        if isinstance(message.data, dict):
            ctx.update(message.data)
        
        tmpl = load_prompt_text(self.config.prompt_file)
        
        if tmpl:
            result = tmpl.format_map(SafeDict(ctx))
            return result
        
        fallback = ctx["message_text"] or str(message.data)
        return fallback
    
    def _extract_message_text(self, message: Message) -> str:
        """Extract message text with comprehensive key search."""
        d = message.data
        if isinstance(d, dict):
            # More comprehensive key list including 'message'
            for k in ("text", "prompt", "input", "query", "content", "message"):
                if isinstance(d.get(k), str):
                    return d[k]
        return str(d)

    def _parse_decision(self, output: str) -> str:
        """Parse the routing decision from LLM output with better fallbacks."""
        if not isinstance(output, str):
            return "STANDARD"  # Better default than None
            
        # Use compiled regex for better performance
        m = _DECISION.search(output)
        if m:
            decision_text = m.group(1).strip()
            # Look for SIMPLE, STANDARD, or COMPLEX in the captured text
            for class_name in ["SIMPLE", "STANDARD", "COMPLEX"]:
                if class_name.upper() in decision_text.upper():
                    return class_name.upper().replace("-", "_")
        
        # Fallback: look for class names anywhere in output
        for class_name in self.classes.keys():
            if class_name.upper() in output.upper():
                return class_name.upper().replace("-", "_")
        
        return "STANDARD"  # Sensible default instead of None
