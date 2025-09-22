from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Callable, Protocol
from time import time
from pathlib import Path
import os
import json

import requests

from .utils import to_display  # para Ollama default

from .types import Message, Result


# --------- Protocolo do LLM ------------
class LLMCallable(Protocol):
    def __call__(self, prompt: str, **kwargs) -> str: ...


@dataclass
class AgentConfig:
    name: str
    retries: int = 0
    retry_backoff_sec: float = 0.0
    model_config: Dict[str, Any] = field(default_factory=dict)
    prompt_file: Optional[str] = None             # caminho/arquivo .md
    tools: List[Any] = field(default_factory=list)


# --------- Helpers de prompt ---------------
def _prompt_dir() -> Path:
    # Pode sobrescrever via env var PROMPT_DIR; default: ./prompts
    return Path(os.environ.get("PROMPT_DIR", "prompts")).resolve()

def load_prompt_text(file_name_or_path: Optional[str]) -> Optional[str]:
    """Carrega texto do prompt a partir de /prompts ou de um path absoluto."""
    if not file_name_or_path:
        return None
    p = Path(file_name_or_path)
    if not p.is_absolute():
        p = _prompt_dir() / file_name_or_path
    if not p.exists():
        raise FileNotFoundError(f"Prompt file not found: {p}")
    return p.read_text(encoding="utf-8")

class SafeDict(dict):
    def __missing__(self, key):
        return ""  # placeholders faltantes viram vazio


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


# ------------- LLMAgent --------------------
class LLMAgent(BaseAgent):
    """
    Usa o SEU LLM (injete via llm_fn) ou, por padrão, Ollama /api/chat.
    Suporta:
      - prompt_file (.md) com placeholders
      - revisão orientada por feedback do crítico (repeat loop)
    Placeholders:
      {root} {previous} {critic_feedback} {iteration} {message_text}
    """
    def __init__(self, config: AgentConfig, llm_fn: Optional[LLMCallable] = None):
        super().__init__(config)
        self.llm_fn = llm_fn or self._default_llm

    # ----------- Default: Ollama chat -----------
    def _default_llm(self, prompt: str, **kwargs) -> str:
        """
        Usa Ollama /api/chat (http://localhost:11434 por padrão).
        model_config suportado:
          - model: str (ex.: "llama3")
          - options: dict (temperature, top_p, etc.)
          - timeout_sec: float
        """
        model_config = self.config.model_config or {}
        model = model_config.get("model", "llama3")
        options = model_config.get("options", {})
        timeout = float(model_config.get("timeout_sec", 120.0))

        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        url = f"{host}/api/chat"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
        }
        if isinstance(options, dict) and options:
            payload["options"] = options

        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Estrutura padrão do /api/chat:
        # { "message": {"role":"assistant","content":"..."} , ... }
        msg = (data or {}).get("message") or {}
        content = msg.get("content")
        if not content:
            # fallback para /api/generate caso o servidor esteja configurado diferente
            gen_url = f"{host}/api/generate"
            gen_payload = {"model": model, "prompt": prompt, "stream": False}
            if isinstance(options, dict) and options:
                gen_payload["options"] = options
            r2 = requests.post(gen_url, json=gen_payload, timeout=timeout)
            r2.raise_for_status()
            d2 = r2.json()
            return (d2 or {}).get("response", "") or ""
        return content

    # ---------------- utilidades ----------------
    def _extract_message_text(self, message: Message) -> str:
        d = message.data
        if isinstance(d, dict):
            for k in ("text", "prompt", "input", "query", "content"):
                if isinstance(d.get(k), str):
                    return d[k]
        return str(d)

    def _build_prompt(self, message: Message) -> str:
        ctx = {
            "root": message.meta.get("root", ""),
            "previous": "",
            "critic_feedback": message.meta.get("critic_feedback", ""),
            "iteration": message.meta.get("iteration", 0),
            "message_text": self._extract_message_text(message),
            # extras comuns para RAG/eval
            "question": (message.data.get("question") if isinstance(message.data, dict) else ""),
            "contexts_md": (message.data.get("contexts_md") if isinstance(message.data, dict) else ""),
            "case_md": (message.data.get("case_md") if isinstance(message.data, dict) else ""),
            "model_output_md": (message.data.get("model_output_md") if isinstance(message.data, dict) else ""),
            "plan_md": (message.data.get("plan_md") if isinstance(message.data, dict) else "")

        }
        if isinstance(message.data, dict) and "previous" in message.data and "input" in message.data:
            ctx["root"] = message.data.get("input", ctx["root"])
            ctx["previous"] = message.data.get("previous", "")

        # Include all keys from message.data in the context for template formatting
        if isinstance(message.data, dict):
            ctx.update(message.data)

        tmpl = load_prompt_text(self.config.prompt_file)
        if tmpl:
            return tmpl.format_map(SafeDict(ctx))
        return ctx["message_text"] or str(message.data)

    
    def run(self, message: Message) -> Result:
        prompt = self._build_prompt(message)
        text = self.llm_fn(prompt, **self.config.model_config)
        #res = Result.ok(output={"text": text}, display_output=text)
        res = Result.ok(output={"text": text}, display_output=to_display(text))
        try:
            res.metrics["prompt_chars"] = len(prompt)
            res.metrics["output_chars"] = len(text or "")
        except Exception:
            pass
        return res
