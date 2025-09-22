import json
import os
import pytest
from src.core.workflow_manager import WorkflowManager
from src.core.agent import AgentConfig, LLMAgent
from src.agents.switch_agent import SwitchAgent
from src.agents.echo import EchoAgent

# Set PROMPT_DIR to the actual prompts directory
os.environ["PROMPT_DIR"] = "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts"

# --- Ollama configuration ---
ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
skip_reason_ollama = "Set OLLAMA_MODEL (e opcional OLLAMA_HOST) para rodar este teste."

def create_ollama_llm_agent() -> LLMAgent:
    """Create LLMAgent that uses real Ollama (no custom llm_fn, uses default)"""
    config = AgentConfig(
        name="OllamaLLM",
        model_config={
            "model": ollama_model or "llama3.2:1b"
        }
    )
    # Don't pass llm_fn - let it use the default Ollama integration
    return LLMAgent(config)

@pytest.mark.skipif(not ollama_model, reason=skip_reason_ollama)
def test_switch_keywords_routing():
    """Test SwitchAgent using keywords mode with LLMAgent using Ollama"""
    # Ensure we use the real prompts directory
    os.environ["PROMPT_DIR"] = "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts"
    
    routes_cfg = {
        "routes": {
            "Billing": {"keywords": ["boleto", "fatura"], "description": "Payment related"},
            "Support": {"keywords": ["erro", "falha"], "description": "Technical support"}, 
            "Sales":   {"keywords": ["preço", "plano"], "description": "Sales inquiries"}
        },
        "default": "Support",
        "mode": "keywords"
    }
    
    # Create LLMAgent that uses real Ollama
    llm_agent = create_ollama_llm_agent()
    
    agents = {
        "Router":  SwitchAgent(AgentConfig(name="Router", model_config=routes_cfg), llm_agent.llm_fn),
        "Billing": EchoAgent(AgentConfig(name="Billing")),
        "Support": EchoAgent(AgentConfig(name="Support")),
        "Sales":   EchoAgent(AgentConfig(name="Sales")),
    }
    graph = {"Router": ["Billing", "Support", "Sales"], "Billing": [], "Support": [], "Sales": []}
    wm = WorkflowManager(graph, agents)

    # Should route to Billing based on "boleto" keyword
    results = wm.run_workflow("Router", {"text": "Quero emitir boleto da minha fatura"})
    assert any(r.output for r in results)
    assert any(r.output.get("route") == "Billing" for r in results if hasattr(r, "output"))
@pytest.mark.skipif(not ollama_model, reason=skip_reason_ollama)
def test_switch_llm_routing():
    """Test SwitchAgent using LLM mode with real Ollama for routing decisions"""
    # Ensure we use the real prompts directory
    os.environ["PROMPT_DIR"] = "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts"
    
    routes_cfg = {
        "routes": {
            "Billing": {"description": "Handle payment issues, invoices, billing questions"},
            "Support": {"description": "Handle technical problems, bugs, system errors"},
            "Sales":   {"description": "Handle pricing questions, plans, purchases"}
        },
        "default": "Support",
        "mode": "llm",
        "confidence_threshold": 0.7
    }
    
    # Create LLMAgent that uses real Ollama
    llm_agent = create_ollama_llm_agent()
    
    agents = {
        "Router":  SwitchAgent(AgentConfig(name="Router", model_config=routes_cfg), llm_agent.llm_fn),
        "Billing": EchoAgent(AgentConfig(name="Billing")),
        "Support": EchoAgent(AgentConfig(name="Support")),
        "Sales":   EchoAgent(AgentConfig(name="Sales")),
    }
    graph = {"Router": ["Billing", "Support", "Sales"], "Billing": [], "Support": [], "Sales": []}
    wm = WorkflowManager(graph, agents)

    # Should use LLM to route to Billing based on payment context
    results = wm.run_workflow("Router", {"text": "I need help with my monthly subscription payment"})
    assert any(r.output for r in results)
    # In LLM mode, the LLM should determine the best route based on context

@pytest.mark.skipif(not ollama_model, reason=skip_reason_ollama)
def test_switch_hybrid_routing():
    """Test SwitchAgent using hybrid mode with real Ollama when keywords fail"""
    # Ensure we use the real prompts directory
    os.environ["PROMPT_DIR"] = "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts"
    
    routes_cfg = {
        "routes": {
            "Billing": {"keywords": ["payment", "invoice"], "description": "Payment related issues"},
            "Support": {"keywords": ["error", "bug"], "description": "Technical support"},
            "Sales":   {"keywords": ["price", "plan"], "description": "Sales inquiries"}
        },
        "default": "Support",
        "mode": "hybrid",
        "confidence_threshold": 0.7
    }
    
    # Create LLMAgent that uses real Ollama for fallback routing
    llm_agent = create_ollama_llm_agent()
    
    agents = {
        "Router":  SwitchAgent(AgentConfig(name="Router", model_config=routes_cfg), llm_agent.llm_fn),
        "Billing": EchoAgent(AgentConfig(name="Billing")),
        "Support": EchoAgent(AgentConfig(name="Support")),
        "Sales":   EchoAgent(AgentConfig(name="Sales")),
    }
    graph = {"Router": ["Billing", "Support", "Sales"], "Billing": [], "Support": [], "Sales": []}
    wm = WorkflowManager(graph, agents)

    # Should fallback to LLM routing when keywords don't match
    results = wm.run_workflow("Router", {"text": "I'm having trouble with my monthly subscription charges"})
    assert any(r.output for r in results)
    # In hybrid mode, should use LLM when keywords don't provide clear match

@pytest.mark.skipif(not ollama_model, reason=skip_reason_ollama)
def test_switch_hybrid_high_confidence():
    """Test SwitchAgent hybrid mode with high confidence LLM using real Ollama"""
    # Ensure we use the real prompts directory
    os.environ["PROMPT_DIR"] = "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts"
    
    routes_cfg = {
        "routes": {
            "Billing": {"keywords": ["fatura", "boleto"], "description": "Handle payment and invoice related queries"},
            "Support": {"keywords": ["erro", "problema"], "description": "Handle technical issues and problems"},
            "Sales":   {"keywords": ["preço", "plano"], "description": "Handle pricing and product inquiries"}
        },
        "default": "Support",
        "mode": "hybrid",
        "confidence_threshold": 0.8  # High threshold
    }
    
    # Create LLMAgent that uses real Ollama for high confidence routing
    llm_agent = create_ollama_llm_agent()
    
    agents = {
        "Router":  SwitchAgent(AgentConfig(name="Router", model_config=routes_cfg), llm_agent.llm_fn),
        "Billing": EchoAgent(AgentConfig(name="Billing")),
        "Support": EchoAgent(AgentConfig(name="Support")),
        "Sales":   EchoAgent(AgentConfig(name="Sales")),
    }
    graph = {"Router": ["Billing", "Support", "Sales"], "Billing": [], "Support": [], "Sales": []}
    wm = WorkflowManager(graph, agents)
    
    results = wm.run_workflow("Router", {"text": "I want to know about your services"})
    assert any(r.output for r in results)
    # With real Ollama LLM, we expect valid routing decisions based on context
