import os
import pathlib
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.approval_gate import ApprovalGateAgent
from tests.test_utils import skip_if_no_ollama, get_test_model_config

@skip_if_no_ollama()
def test_task7_hil_with_ollama():
    model_config = get_test_model_config("standard", temperature=0.1)

    # Gate e Writer
    approval = ApprovalGateAgent(AgentConfig(
        name="ApprovalGate",
        model_config={
            "summary_prompt_file": "approval_request.md",
            "next_on_approve": "Writer",
            **model_config
        }
    ))
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config=model_config
    ))

    agents = {"ApprovalGate": approval, "Writer": writer}
    graph  = {"ApprovalGate": ["Writer"], "Writer": []}

    wm = WorkflowManager(graph, agents)

    # ---- Fase 1: request (HALT) ----
    r1 = wm.run_workflow("ApprovalGate", {"text": "Draft about analytics and funnels."})
    assert any(isinstance(r.output, dict) and r.output.get("status") == "PENDING" for r in r1)
    assert any(("halt" in (r.control or {}) and r.control["halt"]) for r in r1)

    # coleta approval_id
    approval_id = ""
    for r in r1[::-1]:
        if isinstance(r.output, dict) and r.output.get("status") == "PENDING":
            approval_id = r.output.get("approval_id","")
            break
    assert approval_id

    # ---- Fase 2: decision (APPROVE) ----
    r2 = wm.run_workflow("ApprovalGate", {
        "approval_id": approval_id,
        "human_decision": "APPROVE",
        "human_comment": "ok"
    })

    # Deve ter produzido saída do Writer (texto não-vazio)
    final_texts = [r.output.get("text") for r in r2 if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and len(t.strip()) > 0 for t in final_texts)
