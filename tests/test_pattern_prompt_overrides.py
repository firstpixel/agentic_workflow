import os, pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.prompt_switcher import PromptSwitcherAgent

ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason = "Set OLLAMA_MODEL (and optional OLLAMA_HOST) to run this test with real Ollama."

@pytest.mark.skipif(not ollama_model, reason=skip_reason)
def test_task10_prompt_overrides_with_ollama(tmp_path, monkeypatch):
    # Write prompts to disk (no inline prompt strings in code)
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    (prompts / "prompt_switcher.md").write_text(
        "You are a prompt selection assistant.\n\n"
        "### INPUT\n{text}\n\n"
        "### SWITCH RULES\n- If [[PARAGRAPH]] present, choose Writer → writer_paragraph.md\n\n"
        "### OUTPUT\n"
        "### TARGET PROMPTS\n- Writer: writer_paragraph.md\n",
        encoding="utf-8"
    )
    (prompts / "writer_bullets.md").write_text(
        "You are a senior software engineer.\n"
        "Produce a concise technical bullet list only.\n\nINPUT:\n{message_text}\n",
        encoding="utf-8"
    )
    (prompts / "writer_paragraph.md").write_text(
        "You are a senior software engineer.\n"
        "Produce a single concise paragraph.\n\nINPUT:\n{message_text}\n",
        encoding="utf-8"
    )

    monkeypatch.setenv("PROMPT_DIR", str(prompts))

    switcher = PromptSwitcherAgent(AgentConfig(
        name="PromptSwitcher",
        model_config={
            "prompt_file": "prompt_switcher.md",
            "model": ollama_model,
            "options": {"temperature": 0.0},
            "default_targets": {"Writer": "writer_bullets.md"}
        }
    ))
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_bullets.md",
        model_config={"model": ollama_model, "options": {"temperature": 0.1}}
    ))

    agents = {"PromptSwitcher": switcher, "Writer": writer}
    graph  = {"PromptSwitcher": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)

    # Trigger PARAGRAPH selection deterministically
    user_text = {"text": "Explain the API telemetry approach. [[PARAGRAPH]]"}
    results = wm.run_workflow("PromptSwitcher", user_text)

    # Writer should produce some text
    final_texts = [r.output.get("text") for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and len(t.strip()) > 0 for t in final_texts)

    # Ensure Writer's prompt_file was overridden to 'writer_paragraph.md'
    assert writer.config.prompt_file == "writer_paragraph.md"
