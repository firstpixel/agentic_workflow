"""
Model Selector Agent for routing and applying model overrides.
"""
from typing import Dict, Any, Optional
import re
import os

from src.core.agent import BaseAgent, AgentConfig, LLMAgent
from src.core.types import Result, Message

# Compiled regex pattern for better performance and accuracy
_DECISION = re.compile(r"###\s*DECISION\s*\n(.*?)(?=\n###|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)


class ModelSelectorAgent(BaseAgent):
    """
    Agent that selects and applies model configurations based on routing decisions.
    Uses internal LLMAgent with system prompt from config.prompt_file (default: model_router.md)
    
    model_config:
      classes: {"SIMPLE": {...}, "STANDARD": {...}, "COMPLEX": {...}}
      targets: ["agent1", "agent2", ...]
      model: str (for LLMAgent)
    """
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.classes = config.model_config.get("classes", {})
        self.targets = config.model_config.get("targets", [])
        # Create internal LLMAgent - will auto-load system prompt
        self.llm_agent = LLMAgent(config)
    
    def run(self, message: Message) -> Result:
        """
        Run the model selector to determine routing and apply overrides.
        """
        try:
            # Build user prompt with message context
            user_prompt = self._build_user_prompt(message)
            
            # Use LLMAgent to get routing decision
            llm_message = Message(data={"user_prompt": user_prompt}, meta=message.meta)
            result = self.llm_agent.run(llm_message)
            
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
            cfg = {}
            if self.targets:
                cfg = self.classes.get(decision, {})
                if cfg:
                    for target in self.targets:
                        target_overrides[target] = {"model_config": cfg}
            
            # More informative display output
            display_msg = f"🔀 Selector: decision={decision} targets={self.targets}"
            
            # Return result with routing information and user_prompt for downstream LLMAgents
            routing_info = {
                "decision": decision,
                "model_config": cfg if cfg else {},  # Include the config for debugging
                "downstream_agents": list(target_overrides.keys()),
                "md": decision,  # Simplified debug output
                "user_prompt": self._extract_message_text(message),  # Add user_prompt for LLMAgent compatibility
                "text": self._extract_message_text(message)  # Also add text for backward compatibility
            }
            
            return Result(
                success=True,
                output=routing_info,
                display_output=display_msg,
                overrides={"for": target_overrides} if target_overrides else None
            )
            
        except Exception as e:
            return Result(success=False, output=str(e))
    
    def _build_user_prompt(self, message: Message) -> str:
        """Build user prompt with context for new LLMAgent interface."""
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

        # Include all keys from message.data in the context
        if isinstance(message.data, dict):
            ctx.update(message.data)
        
        # Build a comprehensive user prompt with all context
        user_prompt_parts = [
            f"Content to route: {ctx['message_text']}",
        ]
        
        if ctx.get("root"):
            user_prompt_parts.append(f"Original request: {ctx['root']}")
        if ctx.get("previous"):
            user_prompt_parts.append(f"Previous content: {ctx['previous']}")
        if ctx.get("critic_feedback"):
            user_prompt_parts.append(f"Feedback: {ctx['critic_feedback']}")
        if ctx.get("iteration", 0) > 0:
            user_prompt_parts.append(f"Iteration: {ctx['iteration']}")
        
        return "\n\n".join(user_prompt_parts)
    
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
