import os
import pytest

from src.core.agent import AgentConfig, LLMAgent
from src.core.types import Message

# --- Ollama configuration ---
ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason_ollama = "Set OLLAMA_MODEL (e opcional OLLAMA_HOST) para rodar este teste."

@pytest.mark.skipif(not ollama_model, reason=skip_reason_ollama)
def test_llmagent_default_ollama_chat():
    ag = LLMAgent(AgentConfig(
        name="Writer",
        model_config={"model": ollama_model, "options": {"temperature": 0.1}}
    ))  # sem llm_fn => usa _default_llm (Ollama)

    res = ag.execute(Message(data={"text": "Respond with a single short sentence."}))
    assert res.success
    assert isinstance(res.output, dict)
    assert res.output.get("text")
    # Deve vir algum texto não vazio
    assert len(res.output["text"].strip()) > 0
