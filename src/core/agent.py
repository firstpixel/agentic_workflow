from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Callable
from time import time

from .types import Message, Result, AgentExecutionError


@dataclass
class AgentConfig:
    name: str
    retries: int = 0
    retry_backoff_sec: float = 0.0
    model_config: Dict[str, Any] = field(default_factory=dict)  # optional (T9)
    prompt: Optional[str] = None                                # optional (T10)
    tools: List[Any] = field(default_factory=list)              # optional (T5/T6)


class BaseAgent:
    """
    Base contract for all agents. Only 'run' must be overridden.
    'execute' wraps retries, timing and returns a standardized Result.
    """
    def __init__(self, config: AgentConfig):
        self.config = config

    # ---- Overridables -------------------------------------------------
    def run(self, message: Message) -> Result:
        """Implement agent logic here, return Result.ok()/fail()."""
        raise NotImplementedError

    # ---- Execution wrapper (retries, timing, standard result) --------
    def execute(self, message: Message) -> Result:
        start = time()
        attempt = 0
        last_err: Optional[Exception] = None

        while attempt <= self.config.retries:
            try:
                res = self.run(message)
                # Ensure a Result
                if not isinstance(res, Result):
                    res = Result.ok(output=res)
                # Inject basic metrics
                res.metrics.setdefault("agent", self.config.name)
                res.metrics.setdefault("attempt", attempt + 1)
                res.metrics.setdefault("latency_sec", time() - start)
                return res
            except Exception as e:
                last_err = e
                attempt += 1
                if attempt > self.config.retries:
                    break
        # Failed after retries
        return Result.fail(
            output={"error": str(last_err) if last_err else "Unknown error"},
            metrics={"agent": self.config.name, "attempt": attempt, "latency_sec": time() - start}
        )


# ---------- Example LLMAgent with Ollama integration ----------
class LLMAgent(BaseAgent):
    """
    LLM agent with Ollama integration; in later tasks (T5/T9/T10) we plug tools, RAG,
    model selection and prompt overrides.
    """
    def __init__(self, config: AgentConfig, llm_fn: Optional[Callable[..., str]] = None):
        super().__init__(config)
        self.llm_fn = llm_fn or self._default_llm

    def _default_llm(self, prompt: str, **kwargs) -> str:
        """Default Ollama LLM implementation."""
        try:
            import ollama
            
            # Get model from config or use default
            model = kwargs.get("model", "llama3.2:latest")
            
            # Create the chat messages
            messages = [{"role": "user", "content": prompt}]
            
            # Call Ollama
            response = ollama.chat(
                model=model,
                messages=messages,
                stream=False
            )
            
            return response["message"]["content"]
            
        except ImportError:
            return f"[OLLAMA NOT AVAILABLE] {prompt[:120]}"
        except Exception as e:
            return f"[OLLAMA ERROR: {str(e)}] {prompt[:120]}"

    def run(self, message: Message) -> Result:
        prompt = self.config.prompt or message.get("prompt") or str(message.data)
        text = self.llm_fn(prompt, **self.config.model_config)
        return Result.ok(output={"text": text}, display_output=text)
