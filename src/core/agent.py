from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from time import time
from pathlib import Path
import os

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from .utils import to_display
from .types import Message, Result


# --------- Config --------------------------
@dataclass
class AgentConfig:
    name: str
    retries: int = 0
    retry_backoff_sec: float = 0.0
    model_config: Dict[str, Any] = field(default_factory=dict)
    prompt_file: Optional[str] = None  # REQUIRED: markdown path (absolute or relative to PROMPT_DIR)
    tools: List[Any] = field(default_factory=list)
    history_max_messages: int = 8      # NEW: keep last N history messages (default ~4 exchanges)


# --------- Prompt loading (minimal) ---------------
def _prompt_dir() -> Path:
    # PROMPT_DIR can be overridden via env; default ./prompts
    return Path(os.environ.get("PROMPT_DIR", "prompts")).resolve()

def _load_system_prompt_from_config(cfg: AgentConfig) -> str:
    if not cfg.prompt_file:
        raise FileNotFoundError("AgentConfig.prompt_file is required to load the system prompt.")
    p = Path(cfg.prompt_file)
    if not p.is_absolute():
        p = _prompt_dir() / cfg.prompt_file
    if not p.exists():
        raise FileNotFoundError(f"Prompt file not found: {p}")
    return p.read_text(encoding="utf-8")


# ------------- BaseAgent -------------------
class BaseAgent:
    def __init__(self, config: AgentConfig):
        self.config = config

    def run(self, message: Message) -> Result:
        raise NotImplementedError

    def execute(self, message: Message) -> Result:
        start = time()
        attempt = 0
        last_err: Optional[Exception] = None

        while attempt <= self.config.retries:
            try:
                res = self.run(message)
                if not isinstance(res, Result):
                    res = Result.ok(output=res)
                res.metrics.setdefault("agent", self.config.name)
                res.metrics.setdefault("attempt", attempt + 1)
                res.metrics.setdefault("latency_sec", time() - start)
                return res
            except Exception as e:
                last_err = e
                attempt += 1
                if attempt > self.config.retries:
                    break
        return Result.fail(
            output={"error": str(last_err) if last_err else "Unknown error"},
            metrics={"agent": self.config.name, "attempt": attempt, "latency_sec": time() - start}
        )


# ------------- LLMAgent (single-method) --------------------
class LLMAgent(BaseAgent):
    """
    Minimal chat agent.

    Inputs (message.data):
      - user_prompt: str   (required)
      - history: Optional[List[{"role": "user"|"assistant", "content": str}]]

    Behavior:
      - Loads system prompt from config.prompt_file.
      - Builds messages: [system] + trimmed(history) + [current user].
      - Trimming uses config.history_max_messages (default 8).
      - Calls ollama.chat(...) directly (no fallback).
      - Lets exceptions propagate so BaseAgent.execute() can retry if configured.
    """

    def run(self, message: Message) -> Result:
        if not OLLAMA_AVAILABLE:
            raise ImportError("ollama package not available. Install with: pip install ollama")

        # 1) System prompt
        system_prompt = _load_system_prompt_from_config(self.config)

        # 2) Extract user_prompt + history
        if not isinstance(message.data, dict):
            raise ValueError("LLMAgent.run expects message.data to be a dict with 'user_prompt' and optional 'history'.")
        if "user_prompt" not in message.data or not isinstance(message.data["user_prompt"], str):
            raise ValueError("message.data['user_prompt'] (str) is required.")

        user_prompt: str = message.data["user_prompt"]
        history: Optional[List[Dict[str, str]]] = message.data.get("history")

        # Validate and trim history (keep last N messages)
        trimmed_history: List[Dict[str, str]] = []
        if history is not None:
            if not isinstance(history, list):
                raise ValueError("message.data['history'] must be a list of dicts with 'role' and 'content'.")
            for i, turn in enumerate(history):
                if not isinstance(turn, dict) or "role" not in turn or "content" not in turn:
                    raise ValueError(f"Invalid history entry at index {i}: expected dict with 'role' and 'content'.")
            n = self.config.history_max_messages
            if isinstance(n, int) and n > 0 and len(history) > n:
                trimmed_history = history[-n:]
            else:
                trimmed_history = history

        # 3) Build messages: system → trimmed history → current user
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if trimmed_history:
            messages.extend(trimmed_history)
        messages.append({"role": "user", "content": user_prompt})

        # 4) Model + options
        model_cfg = self.config.model_config or {}
        model = model_cfg.get("model", "llama3.2:latest")
        OPT_KEYS = ("temperature", "top_p", "frequency_penalty", "presence_penalty", "num_ctx")
        options = {k: model_cfg[k] for k in OPT_KEYS if k in model_cfg}

        client = ollama.Client(host="http://192.168.1.151:11434")
        # 5) Call Ollama (no streaming)
        response = client.chat(
            model=model,
            messages=messages,
            options=options,
            stream=False,
        )
        try:
            text = (response.get("message") or {}).get("content") or ""
        except Exception as e:
            raise RuntimeError(f"Unexpected Ollama response format: {response}") from e

        # 6) Result
        res = Result.ok(output={"text": text}, display_output=to_display(text))
        res.metrics["input_chars_system"] = len(system_prompt)
        res.metrics["input_chars_user"] = len(user_prompt)
        res.metrics["history_messages_used"] = len(trimmed_history) if trimmed_history else 0
        res.metrics["output_chars"] = len(text)
        return res
