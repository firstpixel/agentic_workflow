from dataclasses import dataclass
from typing import Any
from src.core.agent import BaseAgent, AgentConfig
from src.core.types import Message, Result

class EchoAgent(BaseAgent):
    def run(self, message: Message) -> Result:
        text = f"echo({message.data})"
        return Result.ok(output={"echo": text}, display_output=text)
