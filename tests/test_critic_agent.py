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


# --- helpers para preparar PROMPT_DIR temporário ---
@pytest.fixture(scope="module")
def tmp_prompts(tmp_path_factory):
    d = tmp_path_factory.mktemp("prompts")
    (d / "critic_agent.md").write_text(
        '# Content Evaluation\n\n'
        'You are a meticulous reviewer. Evaluate the TEXT below using the provided RUBRIC criteria.\n\n'
        '**IMPORTANT**: Respond in simple markdown format, NOT JSON. Use this exact structure:\n\n'
        '## Overall Score\n\n'
        '[0-10 number]\n\n'
        '## Detailed Scores\n\n'
        '- [Criterion 1]: [0-10 score]\n\n'
        '## Reasons\n\n'
        '- [Brief reason 1]\n\n'
        '**Evaluation Criteria:**\n{rubric_text}\n\n'
        '**Text to Evaluate:**\n{text}\n\n'
        'Please be thorough but concise in your evaluation.',
        encoding="utf-8"
    )
    os.environ["PROMPT_DIR"] = str(d)
    return d


# --- dummies de LLM para o crítico ---
def critic_llm_low(prompt: str, **kwargs) -> str:
    return "## Overall Score\n\n4.0\n\n## Detailed Scores\n\n- A: 4.0\n\n## Reasons\n\n- Too short"

def critic_llm_high(prompt: str, **kwargs) -> str:
    return "## Overall Score\n\n9.0\n\n## Detailed Scores\n\n- A: 9.0\n\n## Reasons\n\n- Good content"

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

def test_critic_repeat_on_low_score(tmp_prompts):
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


def test_critic_goto_on_pass(tmp_prompts):
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


def test_critic_invalid_markdown_triggers_repeat(tmp_prompts):
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


def test_integration_writer_critic_flow(tmp_prompts):
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
def test_critic_agent_with_ollama(tmp_prompts):
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
    assert "passed" in res.output
    assert "reasons" in res.output
    
    # Check that we got a reasonable score (should be a number between 0-10)
    score = res.output["score"]
    assert isinstance(score, (int, float))
    assert 0 <= score <= 10
    
    print(f"✅ Ollama CriticAgent test passed with score: {score}")
    print(f"   Reasons: {res.output.get('reasons', [])}")
    print(f"   Display: {res.display_output}")