import os, pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.prompt_switcher import PromptSwitcherAgent, PromptAgent
from tests.test_utils import skip_if_no_ollama, get_test_model_config

@skip_if_no_ollama()
def test_task10_prompt_overrides_with_ollama():
    # Use existing prompts from workspace prompts/ folder
    # No need to create temporary files

    model_config_temp0 = get_test_model_config("standard", temperature=0.0)
    model_config_temp01 = get_test_model_config("standard", temperature=0.1)
    
    # Use PromptAgent (alias for PromptSwitcherAgent) with existing prompt_agent.md
    switcher = PromptAgent(AgentConfig(
        name="PromptSwitcher", 
        model_config={
            "prompt_file": "prompt_agent.md",  # Uses existing prompt from prompts/ folder
            **model_config_temp0
        }
    ))
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_bullets.md",  # baseline; should be overridden to writer_paragraph.md
        model_config=model_config_temp01
    ))

    agents = {"PromptSwitcher": switcher, "Writer": writer}
    graph  = {"PromptSwitcher": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)

    # Use [[PARAGRAPH]] trigger to switch to writer_paragraph.md according to prompt_agent.md rules
    user_text = {"text": "[[PARAGRAPH]] Explain the API telemetry approach."}
    results = wm.run_workflow("PromptSwitcher", user_text)

    # Writer should produce some text
    final_texts = [r.output.get("text") for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and len(t.strip()) > 0 for t in final_texts)

    # Ensure Writer's prompt_file was overridden to 'writer_paragraph.md'
    assert writer.config.prompt_file == "writer_paragraph.md"
