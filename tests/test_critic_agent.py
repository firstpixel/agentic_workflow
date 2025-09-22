import os
import json
import pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.types import Message, Result
from src.agents.critic_agent import CriticAgent
from src.core.workflow_manager import WorkflowManager
from src.core.agent import BaseAgent

# --- Ollama configuration ---
ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason_ollama = "Set OLLAMA_MODEL (e opcional OLLAMA_HOST) para rodar este teste."


# --- helpers para configurar PROMPT_DIR ---
@pytest.fixture(scope="module")
def setup_prompts():
    # Use the actual prompts folder
    import pathlib
    prompts_dir = pathlib.Path(__file__).parent.parent / "prompts"
    os.environ["PROMPT_DIR"] = str(prompts_dir)
    return prompts_dir


# --- dummies de LLM para o crítico ---
def critic_llm_low(prompt: str, **kwargs) -> str:
    return "### DECISION\nREVISE\n\n### SCORE\n4.0\n\n### REASONS\n- Too short\n\n### SUGGESTIONS\n- Add more content"

def critic_llm_high(prompt: str, **kwargs) -> str:
    return "### DECISION\nPASS\n\n### SCORE\n9.0\n\n### REASONS\n- Good content\n\n### SUGGESTIONS\n- No changes needed"

def critic_llm_invalid_markdown(prompt: str, **kwargs) -> str:
    return "INVALID_MARKDOWN_FORMAT << " + prompt[:30]


# --- dummy writer (usa LLMAgent com LLM simples) ---
def writer_llm(prompt: str, **kwargs) -> str:
    # finge melhorar o texto (não precisa ser esperto para o teste)
    return "Some structured draft\n## Section\n- point\n## Conclusion\nok"


class DoneAgent(BaseAgent):
    def run(self, message: Message) -> Result:
        return Result.ok(output={"done": True, "from": "Done"}, display_output="✅ Done")


# ------------------ TESTES ----------------------

def test_critic_repeat_on_low_score(setup_prompts):
    critic = CriticAgent(AgentConfig(
        name="Critic",
        model_config={
            "rubric": ["A"], "threshold": 7.5, "max_iters": 2, "prompt_file": "critic_agent.md"
        }
    ), llm_fn=critic_llm_low)

    msg = Message(data={"text": "short"}, meta={"iteration": 0})
    res = critic.execute(msg)
    assert res.success
    assert res.control.get("repeat") is True
    assert res.output["score"] < 7.5


def test_critic_goto_on_pass(setup_prompts):
    critic = CriticAgent(AgentConfig(
        name="Critic",
        model_config={
            "rubric": ["A"], "threshold": 7.5, "max_iters": 2, "next_on_pass": "Done", "prompt_file": "critic_agent.md"
        }
    ), llm_fn=critic_llm_high)

    msg = Message(data={"text": "long enough"}, meta={"iteration": 0})
    res = critic.execute(msg)
    assert res.success
    assert res.control.get("goto") == "Done"
    assert res.output["score"] >= 7.5


def test_critic_invalid_markdown_triggers_repeat(setup_prompts):
    critic = CriticAgent(AgentConfig(
        name="Critic",
        model_config={
            "rubric": ["A"], "threshold": 7.5, "max_iters": 1, "prompt_file": "critic_agent.md"
        }
    ), llm_fn=critic_llm_invalid_markdown)

    msg = Message(data={"text": "anything"}, meta={"iteration": 0})
    res = critic.execute(msg)
    assert res.success
    assert res.control.get("repeat") is True


def test_integration_writer_critic_flow(setup_prompts):
    writer = LLMAgent(AgentConfig(name="Writer", prompt_file=None), llm_fn=writer_llm)
    critic = CriticAgent(AgentConfig(
        name="Critic",
        model_config={
            "rubric": ["A"], "threshold": 7.5, "max_iters": 2, "next_on_pass": "Done", "prompt_file": "critic_agent.md"
        }
    ), llm_fn=critic_llm_high)
    done = DoneAgent(AgentConfig(name="Done"))

    agents = {"Writer": writer, "Critic": critic, "Done": done}
    graph = {"Writer": ["Critic"], "Critic": ["Writer", "Done"], "Done": []}

    wm = WorkflowManager(graph, agents)
    results = wm.run_workflow("Writer", {"prompt": "Write a structured technical summary"})
    # Deve conter uma saída de Done (goto ao aprovar)
    assert any((r.display_output or "").startswith("✅ Done") for r in results)


# --- Helper function to create Ollama LLMAgent ---
def create_ollama_llm_agent() -> LLMAgent:
    """Create LLMAgent that uses real Ollama (no custom llm_fn, uses default)"""
    config = AgentConfig(
        name="OllamaLLM",
        model_config={
            "model": ollama_model or "llama3.2:latest"
        }
    )
    # Don't pass llm_fn - let it use the default Ollama integration
    return LLMAgent(config)

# --- Test with real Ollama ---
@pytest.mark.skipif(not ollama_model, reason=skip_reason_ollama)
def test_critic_agent_with_ollama(setup_prompts):
    """Test CriticAgent using LLMAgent with real Ollama integration."""
    
    # Create LLMAgent that uses real Ollama
    llm_agent = create_ollama_llm_agent()
    
    # Create CriticAgent with LLMAgent's llm_fn
    critic_default = CriticAgent(AgentConfig(
        name="CriticOllama",
        model_config={
            "rubric": ["Clarity and structure", "Technical accuracy"], 
            "threshold": 7.0, 
            "max_iters": 1,
            "prompt_file": "critic_agent.md",
            "model": ollama_model
        }
    ), llm_fn=llm_agent.llm_fn)  # Use LLMAgent's Ollama integration

    # Test with some text
    msg = Message(data={"text": "This is a very detailed and comprehensive technical document with clear structure and accurate information."}, meta={"iteration": 0})
    res = critic_default.execute(msg)
    
    # Basic assertions
    assert res.success, f"CriticAgent with Ollama failed: {res.output}"
    assert isinstance(res.output, dict)
    assert "score" in res.output
    assert "decision" in res.output
    assert "rubric" in res.output
    
    # Check that we got a reasonable score (should be a number between 0-10)
    score = res.output["score"]
    assert isinstance(score, (int, float))
    assert 0 <= score <= 10
    
    # Check decision is valid
    decision = res.output["decision"]
    assert decision in ["PASS", "REVISE"]
    
    print(f"✅ Ollama CriticAgent test passed with score: {score}, decision: {decision}")
    print(f"   Display: {res.display_output}")