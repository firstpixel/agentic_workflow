# config/settings.py
from __future__ import annotations
from dataclasses import dataclass
import os
from typing import Optional

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1","true","t","yes","y","on")

def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    try:
        return float(v) if v is not None else default
    except Exception:
        return default

@dataclass
class Settings:
    # LLM
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    ollama_simple_model: str = "llama3.2:1b"
    ollama_standard_model: str = "llama3.2:3b"
    ollama_complex_model: str = "gemma3:latest"
    ollama_coder_model: str = "qwen3-coder"
    ollama_timeout_sec: float = 120.0

    # Prompts
    prompt_dir: str = "prompts"

    # Memory/RAG (quando aplicável)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "app"

    # EventBus
    eventbus_enabled: bool = True
    eventbus_default_channel: str = "app.events"

    # Misc
    debug: bool = _env_bool("DEBUG", False)  # noqa

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2:1b"),
            ollama_simple_model=os.environ.get("OLLAMA_SIMPLE_MODEL", "llama3.2:1b"),
            ollama_standard_model=os.environ.get("OLLAMA_STANDARD_MODEL", "llama3.2:3b"),
            ollama_complex_model=os.environ.get("OLLAMA_COMPLEX_MODEL", "gemma3:latest"),
            ollama_coder_model=os.environ.get("OLLAMA_CODER_MODEL", "qwen3-coder"),
            ollama_timeout_sec=_env_float("OLLAMA_TIMEOUT_SEC", 120.0),
            prompt_dir=os.environ.get("PROMPT_DIR", "prompts"),
            qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.environ.get("QDRANT_API_KEY"),
            mongo_uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
            mongo_db=os.environ.get("MONGO_DB", "app"),
            eventbus_enabled=_env_bool("EVENTBUS_ENABLED", True),
            eventbus_default_channel=os.environ.get("EVENTBUS_DEFAULT_CHANNEL", "app.events"),
            debug=_env_bool("DEBUG", False),
        )

# singleton simples
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings
