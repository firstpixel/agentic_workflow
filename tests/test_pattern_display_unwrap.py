import os
import pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.core.utils import to_display
from tests.test_utils import get_test_model_config, skip_if_no_ollama

@skip_if_no_ollama()
def test_display_unwrap_with_ollama(tmp_path, monkeypatch):
    # prompts em arquivos
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    # writer_unwrap.md força saída com cerca de código e espaços variados
    (prompts / "writer_unwrap.md").write_text(
        "You are a helpful assistant.\n"
        "When the user says anything, return the following EXACT format including the triple backticks:\n\n"
        "```\n"
        "Line 1: Hello, API telemetry!\n"
        "\n"
        "   Line 2 with trailing spaces   \n"
        "```\n\n"
        "IMPORTANT: Include the triple backticks (```) at the beginning and end.",
        encoding="utf-8"
    )
    monkeypatch.setenv("PROMPT_DIR", str(prompts))

    model_config = get_test_model_config("standard", temperature=0.0)
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_unwrap.md",
        model_config=model_config
    ))
    agents = {"Writer": writer}
    graph = {"Writer": []}
    wm = WorkflowManager(graph, agents)

    msg = {"user_prompt": "Hello, API telemetry!"}
    results = wm.run_workflow("Writer", msg)

    # Deve existir um output textual do Writer
    outs = [r for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert outs, "Expected at least one LLMAgent output"
    raw = outs[-1].output["text"]
    disp = outs[-1].display_output

    # display_output deve estar sem cercas de código e sem espaços excedentes
    assert "```" not in disp, "display_output should have fences stripped"
    assert "trailing spaces   " not in disp, "display_output should normalize trailing spaces"

    # O output cru continua como veio do LLM (com as cercas)
    assert "```" in raw, "raw LLM output should be untouched"
    # to_display aplicado manualmente também remove cerca
    assert "```" not in to_display(None, raw)
