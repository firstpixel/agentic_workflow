from __future__ import annotations
from dataclasses import dataclass, field
import os
from typing import Optional, ClassVar

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "t", "yes", "y", "on"}

def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default

@dataclass(frozen=True)
class Settings:
    # LLM
    ollama_host: str = field(default="http://localhost:11434")
    ollama_model: str = field(default="llama3.2:1b")
    ollama_simple_model: str = field(default="llama3.2:1b")
    ollama_standard_model: str = field(default="llama3.2:3b")
    ollama_complex_model: str = field(default="gemma3:latest")
    ollama_coder_model: str = field(default="qwen3-coder")
    ollama_timeout_sec: float = field(default=120.0)

    # Prompts
    prompt_dir: str = field(default="prompts")

    # Memory/RAG (quando aplicável)
    qdrant_url: str = field(default="http://localhost:6333")
    qdrant_api_key: Optional[str] = field(default=None)
    mongo_uri: str = field(default="mongodb://localhost:27017")
    mongo_db: str = field(default="app")

    # EventBus
    eventbus_enabled: bool = field(default=True)
    eventbus_default_channel: str = field(default="app.events")

    # Misc
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))

    # Singleton instance
    _instance: ClassVar[Optional["Settings"]] = None

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
            debug=_env_bool("DEBUG", True),
        )

def get_settings() -> Settings:
    if Settings._instance is None:
        Settings._instance = Settings.load()
    return Settings._instance

def reset_settings():
    """Reset settings singleton - useful for testing"""
    Settings._instance = None

def get_model_config(model_type: str = "standard", **extra_options) -> dict:
    """
    Get model configuration from settings.
    
    Args:
        model_type: One of 'simple', 'standard', 'complex', 'coder', or 'default'
        **extra_options: Additional options to merge into the config
    
    Returns:
        Dict with model configuration
    """
    settings = get_settings()
    
    model_map = {
        "simple": settings.ollama_simple_model,
        "standard": settings.ollama_standard_model,
        "complex": settings.ollama_complex_model,
        "coder": settings.ollama_coder_model,
        "default": settings.ollama_model,
    }
    
    model = model_map.get(model_type, settings.ollama_model)
    
    config = {
        "model": model,
        "host": settings.ollama_host,
        "timeout": settings.ollama_timeout_sec,
    }
    
    # Add any extra options
    if extra_options:
        config.update(extra_options)
    
    return config

def should_skip_ollama_test() -> tuple[bool, str]:
    """
    Check if Ollama tests should be skipped.
    Returns (should_skip, reason)
    """
    settings = get_settings()
    # We now have defaults, so we don't need to skip unless explicitly disabled
    # But for backwards compatibility, still check if OLLAMA_MODEL is set to empty string
    if os.environ.get("OLLAMA_MODEL", None) == "":
        return True, "OLLAMA_MODEL explicitly set to empty string"
    return False, ""

def get_database_config() -> dict:
    """Get database configuration from settings"""
    settings = get_settings()
    return {
        "mongo_uri": settings.mongo_uri,
        "mongo_db": settings.mongo_db,
        "qdrant_url": settings.qdrant_url,
        "qdrant_api_key": settings.qdrant_api_key,
    }