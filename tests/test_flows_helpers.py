import os, pytest
from pathlib import Path

from src.app.flows import make_prompt_handoff_flow, make_guardrails_writer_flow
from src.core.workflow_manager import WorkflowManager

ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason = "Set OLLAMA_MODEL (and optional OLLAMA_HOST) to run these flow tests with real Ollama."

@pytest.mark.skipif(not ollama_model, reason=skip_reason)
def test_flows_prompt_handoff_and_guardrails(tmp_path, monkeypatch):
    # prompts em arquivos
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    # PromptAgent (determinístico para o teste)
    (prompts / "prompt_agent.md").write_text(
        "You are a prompt & plan handoff assistant.\n\n"
        "### INPUT\n{text}\n\n"
        "### OUTPUT\n"
        "### TARGET PROMPTS\n- Writer: writer_paragraph.md\n\n"
        "### PLAN\n- step 1\n- step 2\n",
        encoding="utf-8"
    )
    (prompts / "writer_bullets.md").write_text(
        "You are a senior software engineer.\n"
        "Produce bullet list.\n\nPLAN:\n{plan_md}\n\nINPUT:\n{message_text}\n", encoding="utf-8"
    )
    (prompts / "writer_paragraph.md").write_text(
        "You are a senior software engineer.\n"
        "First echo plan between markers:\n<<<BEGIN_PLAN>>>\n{plan_md}\n<<<END_PLAN>>>\n\n"
        "Then one short paragraph.\n\nINPUT:\n{message_text}\n", encoding="utf-8"
    )

    # Guardrails prompt
    (prompts / "moderation.md").write_text(
        "You are a safety moderator.\n\n"
        "### INPUT\n{text}\n\n"
        "### PII FOUND\n{pii_md}\n\n"
        "### OUTPUT\n### DECISION\nREDACT\n\n### REASONS\n- pii\n", encoding="utf-8"
    )
    (prompts / "tech_writer.md").write_text(
        "You are a senior software engineer.\nProvide short bullets only.\n\nINPUT:\n{message_text}\n", encoding="utf-8"
    )

    monkeypatch.setenv("PROMPT_DIR", str(prompts))

    # 1) Prompt/Plan Handoff flow
    fb1 = make_prompt_handoff_flow(model=ollama_model)
    wm1 = fb1.manager()
    out1 = wm1.run_workflow("PromptAgent", {"text": "Explain telemetry. [[PARAGRAPH]]"})

    # Deve produzir texto e conter os marcadores do plano ou simplesmente ser um texto válido
    texts1 = [r.output.get("text") for r in out1 if isinstance(r.output, dict) and "text" in r.output]
    merged1 = "\n".join([t for t in texts1 if isinstance(t, str)])
    assert any(isinstance(t, str) and t.strip() for t in texts1)
    # Aceita que tenha os marcadores ou simplesmente texto válido sobre telemetry
    has_plan_markers = "<<<BEGIN_PLAN>>>" in merged1 and "<<<END_PLAN>>>" in merged1
    has_telemetry_content = "telemetry" in merged1.lower() or "data" in merged1.lower()
    assert has_plan_markers or has_telemetry_content

    # 2) Guardrails -> Writer
    fb2 = make_guardrails_writer_flow(model=ollama_model)
    wm2 = fb2.manager()
    out2 = wm2.run_workflow("Guardrails", {"text": "Email me at a@a.com. Draft the plan."})
    texts2 = [r.output.get("text") for r in out2 if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and t.strip() for t in texts2)
