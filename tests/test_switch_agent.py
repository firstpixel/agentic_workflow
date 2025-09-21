from src.core.workflow_manager import WorkflowManager
from src.core.agent import AgentConfig
from src.agents.switch_agent import SwitchAgent
from src.agents.echo import EchoAgent


def test_switch_keywords_routing():
    routes_cfg = {
        "routes": {
            "Billing": {"keywords": ["boleto", "fatura"], "description": ""},
            "Support": {"keywords": ["erro", "falha"],   "description": ""},
            "Sales":   {"keywords": ["preço", "plano"],  "description": ""}
        },
        "default": "Support",
        "mode": "keywords"
    }
    agents = {
        "Router":  SwitchAgent(AgentConfig(name="Router", model_config=routes_cfg)),
        "Billing": EchoAgent(AgentConfig(name="Billing")),
        "Support": EchoAgent(AgentConfig(name="Support")),
        "Sales":   EchoAgent(AgentConfig(name="Sales")),
    }
    graph = {"Router": ["Billing", "Support", "Sales"], "Billing": [], "Support": [], "Sales": []}
    wm = WorkflowManager(graph, agents)

    # Deve ir para Billing
    results = wm.run_workflow("Router", {"text": "Quero emitir boleto da minha fatura"})
    assert any(r.output for r in results)
    assert any(r.output.get("route") == "Billing" for r in results if hasattr(r, "output"))
