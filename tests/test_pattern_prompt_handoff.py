import os
import pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.prompt_agent import PromptAgent  # agente do Task 10 (Prompt/Plan Handoff)

ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason = "Set OLLAMA_MODEL (and optional OLLAMA_HOST) to run this test with real Ollama."

@pytest.mark.skipif(not ollama_model, reason=skip_reason)
def test_task10_prompt_handoff_with_ollama(tmp_path, monkeypatch):
    # ---------- prompts em ARQUIVOS (nada inline) ----------
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    # prompt do PromptAgent: determinístico para este teste
    (prompts / "prompt_agent.md").write_text(
        "You are a prompt & plan handoff assistant.\n\n"
        "### INPUT\n{text}\n\n"
        "### OUTPUT\n"
        "### TARGET PROMPTS\n- Writer: writer_paragraph.md\n\n"
        "### PLAN\n"
        "- step 1: set up tracking\n"
        "- step 2: collect events\n"
        "- step 3: aggregate\n"
        "- step 4: report\n",
        encoding="utf-8"
    )

    # writer_bullets.md (baseline, não será usado pois haverá override para paragraph)
    (prompts / "writer_bullets.md").write_text(
        "You are a senior software engineer.\n"
        "Produce a concise technical bullet list only.\n\n"
        "PLAN:\n{plan_md}\n\n"
        "INPUT:\n{message_text}\n",
        encoding="utf-8"
    )

    # writer_paragraph.md (vai ser escolhido pelo PromptAgent)
    # Forçamos o writer a **ecoar o plano** entre marcadores para validar o handoff.
    (prompts / "writer_paragraph.md").write_text(
        "You are a senior software engineer.\n"
        "First print exactly the plan between the markers below.\n"
        "Print exactly:\n"
        "<<<BEGIN_PLAN>>>\n"
        "{plan_md}\n"
        "<<<END_PLAN>>>\n\n"
        "Now write one short paragraph summary.\n\n"
        "INPUT:\n{message_text}\n",
        encoding="utf-8"
    )

    monkeypatch.setenv("PROMPT_DIR", str(prompts))

    # ---------- pipeline ----------
    prompt_agent = PromptAgent(AgentConfig(
        name="PromptAgent",
        model_config={
            "prompt_file": "prompt_agent.md",
            "model": ollama_model,
            "options": {"temperature": 0.0},
            # default_targets não é necessário neste teste pois o prompt já fixa o TARGET
        }
    ))

    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_bullets.md",  # baseline; será overriden para writer_paragraph.md
        model_config={"model": ollama_model, "options": {"temperature": 0.0}}
    ))

    agents = {"PromptAgent": prompt_agent, "Writer": writer}
    graph = {"PromptAgent": ["Writer"], "Writer": []}

    wm = WorkflowManager(graph, agents)

    # ---------- execução ----------
    user_text = {"text": "Design telemetry for API request/latency and error rates."}
    results = wm.run_workflow("PromptAgent", user_text)

    # ---------- asserções ----------
    # 1) Writer deve ter sido executado e ter texto final
    finals = [r.output.get("text") for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and len(t.strip()) > 0 for t in finals), "Expected non-empty writer output"

    # 2) Verifica que o prompt do Writer foi override para writer_paragraph.md
    assert writer.config.prompt_file == "writer_paragraph.md", "Writer prompt_file should be overridden to writer_paragraph.md"

    # 3) Verifica que o plano foi repassado (procura marcadores e uma etapa do plano)
    merged_text = "\n".join([t for t in finals if isinstance(t, str)])
    assert "<<<BEGIN_PLAN>>>" in merged_text and "<<<END_PLAN>>>" in merged_text, "Expected plan markers in writer output"
    assert "step 1: set up tracking" in merged_text, "Expected at least one plan bullet echoed by writer"
