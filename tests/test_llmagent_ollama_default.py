import os
import pytest

from src.core.agent import AgentConfig, LLMAgent
from src.core.types import Message
from tests.test_utils import get_test_model_config, should_skip_ollama_test

skip_reason_ollama = "Set OLLAMA_MODEL (e opcional OLLAMA_HOST) para rodar este teste."

# Get skip condition from centralized settings
should_skip, skip_reason = should_skip_ollama_test()

@pytest.mark.skipif(should_skip, reason=skip_reason or skip_reason_ollama)
def test_llmagent_default_ollama_chat(tmp_path, monkeypatch):
    # Create a temporary prompt file
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    
    (prompts / "simple_writer.md").write_text(
        "You are a helpful assistant. Respond with a single short sentence.",
        encoding="utf-8"
    )
    
    # Set the prompt directory to our temporary location
    monkeypatch.setenv("PROMPT_DIR", str(prompts))
    
    # Get model config from centralized test utilities
    model_config = get_test_model_config("standard", temperature=0.1)
    
    ag = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="simple_writer.md",
        model_config=model_config
    )) 

    res = ag.execute(Message(data={"user_prompt": "Say hello briefly."}))
    assert res.success
    assert isinstance(res.output, dict)
    assert res.output.get("text")
    # Deve vir algum texto não vazio
    assert len(res.output["text"].strip()) > 0
