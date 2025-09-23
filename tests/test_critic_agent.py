import os
import json
import pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.types import Message, Result
from src.agents.critic_agent import CriticAgent
from src.core.workflow_manager import WorkflowManager
from src.core.agent import BaseAgent
from tests.test_utils import setup_prompts, get_test_model_config, skip_if_no_ollama


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
        prompt_file="critic_agent.md",
        model_config={
            "rubric": ["A"], "threshold": 7.5, "max_iters": 2
        }
    ))
    # Override internal LLM agent for testing
    critic.llm_agent.run = lambda msg: Result.ok(output={"text": critic_llm_low(msg.data["user_prompt"])})

    msg = Message(data={"text": "short"}, meta={"iteration": 0})
    res = critic.execute(msg)
    assert res.success
    assert res.control.get("repeat") is True
    assert res.output["score"] < 7.5


def test_critic_goto_on_pass(setup_prompts):
    critic = CriticAgent(AgentConfig(
        name="Critic",
        prompt_file="critic_agent.md",
        model_config={
            "rubric": ["A"], "threshold": 7.5, "max_iters": 2, "next_on_pass": "Done"
        }
    ))
    # Override internal LLM agent for testing
    critic.llm_agent.run = lambda msg: Result.ok(output={"text": critic_llm_high(msg.data["user_prompt"])})

    msg = Message(data={"text": "long enough"}, meta={"iteration": 0})
    res = critic.execute(msg)
    assert res.success
    assert res.control.get("goto") == "Done"
    assert res.output["score"] >= 7.5


def test_critic_invalid_markdown_triggers_repeat(setup_prompts):
    critic = CriticAgent(AgentConfig(
        name="Critic",
        prompt_file="critic_agent.md",
        model_config={
            "rubric": ["A"], "threshold": 7.5, "max_iters": 1
        }
    ))
    # Override internal LLM agent for testing
    critic.llm_agent.run = lambda msg: Result.ok(output={"text": critic_llm_invalid_markdown(msg.data["user_prompt"])})

    msg = Message(data={"text": "anything"}, meta={"iteration": 0})
    res = critic.execute(msg)
    assert res.success
    assert res.control.get("repeat") is True


def test_integration_writer_critic_flow(setup_prompts):
    writer = LLMAgent(AgentConfig(name="Writer", prompt_file="tech_writer.md"))
    # Override writer for testing
    writer.run = lambda msg: Result.ok(output={"text": writer_llm(msg.data["user_prompt"])})
    
    critic = CriticAgent(AgentConfig(
        name="Critic",
        prompt_file="critic_agent.md",
        model_config={
            "rubric": ["A"], "threshold": 7.5, "max_iters": 2, "next_on_pass": "Done"
        }
    ))
    # Override internal LLM agent for testing
    critic.llm_agent.run = lambda msg: Result.ok(output={"text": critic_llm_high(msg.data["user_prompt"])})
    
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
    model_config = get_test_model_config("standard")
    config = AgentConfig(
        name="OllamaLLM",
        model_config=model_config
    )
    # Don't pass llm_fn - let it use the default Ollama integration
    return LLMAgent(config)

# --- Test with real Ollama ---
@skip_if_no_ollama()
def test_critic_agent_with_ollama(setup_prompts):
    """Test CriticAgent using LLMAgent with real Ollama integration."""
    
    # Create LLMAgent that uses real Ollama
    llm_agent = create_ollama_llm_agent()
    
    # Create CriticAgent with proper configuration
    model_config = get_test_model_config("standard")
    model_config.update({
        "rubric": ["Clarity and structure", "Technical accuracy"], 
        "threshold": 7.0, 
        "max_iters": 1,
    })
    
    critic_default = CriticAgent(AgentConfig(
        name="CriticOllama",
        prompt_file="critic_agent.md",
        model_config=model_config
    ))  # Uses internal LLMAgent for Ollama integration

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