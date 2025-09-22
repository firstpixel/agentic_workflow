import os, pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.model_selector import ModelSelectorAgent

ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason = "Set OLLAMA_MODEL (and optional OLLAMA_HOST) to run this test with real Ollama."

@pytest.mark.skipif(not ollama_model, reason=skip_reason)
def test_task9_model_routing_applies_overrides(tmp_path, monkeypatch):
    # Write prompts to disk (no inline temp prompts)
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    (prompts / "model_router.md").write_text(
        "You are a resource-aware model router.\n\n"
        "### INPUT\n{text}\n\n"
        "### ROUTING RULES\n- If [[SIMPLE]] present, decide SIMPLE.\n\n"
        "### OUTPUT\n"
        "### DECISION\nSIMPLE\n\n"
        "### TARGETS\n- Writer: SIMPLE\n",
        encoding="utf-8"
    )

    (prompts / "tech_writer.md").write_text(
        "You are a senior software engineer.\n"
        "Produce a concise technical bullet list only.\n\nINPUT:\n{message_text}\n",
        encoding="utf-8"
    )

    monkeypatch.setenv("PROMPT_DIR", str(prompts))

    # Router with classes mapping
    router = ModelSelectorAgent(AgentConfig(
        name="ModelSelector",
        model_config={
            "prompt_file": "model_router.md",
            "model": ollama_model,
            "options": {"temperature": 0.0},
            "classes": {
                "SIMPLE":   {"model": ollama_model, "options": {"temperature": 0.1}},
                "STANDARD": {"model": ollama_model, "options": {"temperature": 0.3}},
                "COMPLEX":  {"model": ollama_model, "options": {"temperature": 0.6}}
            },
            "targets": ["Writer"]
        }
    ))

    # Writer baseline (will be overridden)
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config={"model": ollama_model, "options": {"temperature": 0.4}}
    ))

    agents = {"ModelSelector": router, "Writer": writer}
    graph  = {"ModelSelector": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)

    # Input contains [[SIMPLE]] to force SIMPLE decision deterministically
    user_text = {"text": "Please summarize the design very briefly. [[SIMPLE]]"}
    results = wm.run_workflow("ModelSelector", user_text)

    # Writer should have been executed and used; ensure it produced text
    final_texts = [r.output.get("text") for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and len(t.strip()) > 0 for t in final_texts)

    # Check that Writer's model_config was overridden to SIMPLE (temperature 0.1)
    assert isinstance(writer.config.model_config, dict)
    assert writer.config.model_config.get("options", {}).get("temperature") == 0.1
