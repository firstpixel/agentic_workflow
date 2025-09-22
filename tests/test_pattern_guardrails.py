import os, pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.guardrails_agent import GuardrailsAgent

ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason = "Set OLLAMA_MODEL (and optional OLLAMA_HOST) to run this test with real Ollama."

@pytest.mark.skipif(not ollama_model, reason=skip_reason)
def test_task6_guardrails_with_ollama():
    # Use existing prompt files from prompts/ directory

    guard = GuardrailsAgent(AgentConfig(
        name="Guardrails",
        model_config={
            "pii_redact": True,
            "moderation_mode": "hybrid",
            "moderation_prompt_file": "moderation.md",
            "model": ollama_model,
            "options": {"temperature": 0.0}
        }
    ))

    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config={"model": ollama_model, "options": {"temperature": 0.1}}
    ))

    agents = {"Guardrails": guard, "Writer": writer}
    graph  = {"Guardrails": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)

    user_text = {"text": "Contact me at jane@company.com or +55 11 99999-0000. Outline the technical plan."}
    results = wm.run_workflow("Guardrails", user_text)

    # Deve ter redigido PII em pelo menos uma etapa
    redacted_present = any(
        isinstance(r.output, dict) and isinstance(r.output.get("text"), str) and
        ("[[REDACTED:EMAIL]]" in r.output["text"] or "[[REDACTED:PHONE]]" in r.output["text"])
        for r in results
    )
    assert redacted_present, "Expected PII redaction markers in guardrails output"

    # Deve existir texto produzido pelo writer (LLM real)
    final_texts = [r.output.get("text") for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and len(t.strip()) > 0 for t in final_texts)
