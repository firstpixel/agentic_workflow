import os
import pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.prompt_switcher import PromptAgent  # Unified agent (alias for PromptSwitcherAgent)
from tests.test_utils import skip_if_no_ollama, get_test_model_config

@skip_if_no_ollama()
def test_task10_prompt_handoff_with_ollama():
    # Use existing prompts from workspace prompts/ folder
    # No need to create temporary files

    model_config = get_test_model_config("standard", temperature=0.0)
    
    # ---------- pipeline ----------
    prompt_agent = PromptAgent(AgentConfig(
        name="PromptAgent",
        model_config={
            "prompt_file": "prompt_agent.md",  # Uses existing prompt from prompts/ folder
            **model_config
        }
    ))

    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_bullets.md",  # baseline; should be overridden to writer_paragraph.md
        model_config=model_config
    ))

    agents = {"PromptAgent": prompt_agent, "Writer": writer}
    graph = {"PromptAgent": ["Writer"], "Writer": []}

    wm = WorkflowManager(graph, agents)

    # ---------- execução ----------
    # Use [[PARAGRAPH]] trigger to switch to writer_paragraph.md according to prompt_agent.md rules
    user_text = {"text": "[[PARAGRAPH]] Design telemetry for API request/latency and error rates."}
    results = wm.run_workflow("PromptAgent", user_text)

    # ---------- asserções ----------
    # 1) Writer deve ter sido executado e ter texto final
    finals = [r.output.get("text") for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and len(t.strip()) > 0 for t in finals), "Expected non-empty writer output"

    # 2) Verifica que o prompt do Writer foi override para writer_paragraph.md
    assert writer.config.prompt_file == "writer_paragraph.md", f"Writer prompt_file should be writer_paragraph.md, got: {writer.config.prompt_file}"
    
    # 3) Verifica que a troca de prompt funcionou - deve ser paragraph format (não bullet)
    merged_text = "\n".join([t for t in finals if isinstance(t, str)])
    assert len(merged_text) > 20, f"Expected substantial output from paragraph writer, got: {len(merged_text)} chars"
    
    # 4) Verify the prompt switching worked - paragraph format should be flowing text
    # writer_paragraph.md asks for "single concise paragraph", not bullet list
    # So it should NOT start with bullet markers like "- " or "* "
    lines = merged_text.strip().split('\n')
    first_content_line = next((line.strip() for line in lines if line.strip()), "")
    assert not first_content_line.startswith(('-', '*', '•')), f"Expected paragraph format, got bullet-like format: {first_content_line[:50]}"