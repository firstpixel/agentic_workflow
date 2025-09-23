"""
Test utilities for centralized configuration management.
"""
import pytest
import os
from pathlib import Path
from src.config.settings import get_settings, get_model_config, should_skip_ollama_test, get_database_config


def setup_test_environment():
    """Set up test environment with proper prompt directory."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    os.environ["PROMPT_DIR"] = str(prompts_dir)
    return prompts_dir


def get_test_model_config(model_type="standard", temperature=0.1, **kwargs):
    """Get model configuration for tests."""
    config = get_model_config(model_type)
    config["options"] = config.get("options", {})
    config["options"]["temperature"] = temperature
    
    # Merge any additional kwargs
    for key, value in kwargs.items():
        config[key] = value
    
    return config


def skip_if_no_ollama():
    """Decorator to skip tests if Ollama is not available."""
    should_skip, reason = should_skip_ollama_test()
    return pytest.mark.skipif(should_skip, reason=reason)


def skip_if_no_databases():
    """Decorator to skip tests if databases are not available."""
    db_config = get_database_config()
    # For tests, we use default localhost URLs, so no need to skip
    # unless explicitly set to empty
    mongo_empty = os.environ.get("MONGO_URI", None) == ""
    qdrant_empty = os.environ.get("QDRANT_URL", None) == ""
    
    should_skip = mongo_empty or qdrant_empty
    reason = "Database URLs explicitly disabled"
    
    return pytest.mark.skipif(should_skip, reason=reason)


def get_test_database_config():
    """Get database configuration for tests."""
    return get_database_config()


# Common fixtures
@pytest.fixture(scope="module")
def setup_prompts():
    """Set up prompts directory for tests."""
    return setup_test_environment()


@pytest.fixture
def test_model_config():
    """Provide standard test model configuration."""
    return get_test_model_config()


@pytest.fixture
def test_db_config():
    """Provide test database configuration."""
    return get_test_database_config()