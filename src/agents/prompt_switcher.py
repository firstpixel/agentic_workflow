from __future__ import annotations
from typing import Any, Dict
import re

from src.core.agent import BaseAgent, AgentConfig, LLMAgent
from src.core.types import Message, Result

# --------- Markdown parsers ----------
_TARGET_PROMPTS = re.compile(
    r"^###\s*TARGET\s+PROMPTS\s*\n(?P<body>.*?)(?=^\s*###\s+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL
)

def _parse_target_prompts(md: str) -> Dict[str, str]:
    """
    Parse lines under '### TARGET PROMPTS' of the form:
      - AgentName: file_name.md
    Returns: {'AgentName': 'file_name.md', ...}
    """
    out: Dict[str, str] = {}
    m = _TARGET_PROMPTS.search(md or "")
    if not m:
        return out
    body = (m.group("body") or "").strip()
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        s = s.lstrip("-• \t")
        # Accept "Writer: writer_paragraph.md" or "Writer writer_paragraph.md"
        if ":" in s:
            k, v = s.split(":", 1)
            out[k.strip()] = v.strip()
        else:
            parts = s.split()
            if len(parts) >= 2:
                out[parts[0].strip()] = parts[1].strip()
    return out


class PromptSwitcherAgent(BaseAgent):
    """
    Decides prompt files to use downstream and emits targeted overrides.

    model_config:
      {
        "prompt_file": "prompt_switcher.md",  # REQUIRED
        "model": "...", "options": {...},     # forwarded to LLMAgent
        # Optional: default_targets applied when TARGET PROMPTS section is empty
        "default_targets": {"Writer": "writer_bullets.md"}
      }

    Output:
      Result.overrides["for"] = {
        "<AgentName>": {"prompt_file": "<file.md>"}
      }
    """
    def __init__(self, config: AgentConfig):
        super().__init__(config)

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, dict):
            for k in ("text","prompt","input","query","content","message"):
                v = data.get(k)
                if isinstance(v, str):
                    return v
        return str(data)

    def run(self, message: Message) -> Result:
        mc = self.config.model_config or {}
        prompt_file = mc.get("prompt_file")
        if not prompt_file:
            raise ValueError("PromptSwitcherAgent requires model_config['prompt_file'] (e.g., 'prompt_switcher.md').")

        # Use LLMAgent to generate the Markdown decision (reusing your Ollama integration)
        llm = LLMAgent(AgentConfig(
            name=f"{self.config.name}::LLM",
            prompt_file=prompt_file,
            model_config=mc
        ))
        text = self._extract_text(message.data)
        md = llm.execute(Message(data={"text": text})).output.get("text", "")

        targets = _parse_target_prompts(md)
        if not targets:
            # apply fallback defaults if provided
            targets = dict(mc.get("default_targets") or {})

        # Convert to targeted overrides for WorkflowManager (Task 9)
        targeted = {agent_name: {"prompt_file": file_name} for agent_name, file_name in targets.items()}

        disp = f"🧭 PromptSwitcher -> {targets}"
        return Result.ok(
            output={"targets": targets, "md": md},
            display_output=disp,
            overrides={"for": targeted} if targeted else {}
        )
