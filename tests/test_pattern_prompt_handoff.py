import os
import pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.prompt_switcher import PromptAgent  # Unified agent (alias for PromptSwitcherAgent)
from tests.test_utils import skip_if_no_ollama, get_test_model_config

@skip_if_no_ollama()
def test_task10_prompt_handoff_with_ollama(tmp_path, monkeypatch):
    # ---------- prompts em ARQUIVOS (nada inline) ----------
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    # prompt do PromptAgent: determinístico para este teste
    (prompts / "prompt_agent.md").write_text(
        "You must output EXACTLY this text with no modifications, additions, or creative content:\n\n"
        "### TARGET PROMPTS\n"
        "- Writer: writer_paragraph.md\n\n"
        "### PLAN\n"
        "- step 1: set up tracking\n"
        "- step 2: collect events\n" 
        "- step 3: aggregate\n"
        "- step 4: report\n\n"
        "INPUT: {user_prompt}\n\n"
        "OUTPUT (copy exactly):\n"
        "### TARGET PROMPTS\n"
        "- Writer: writer_paragraph.md\n\n"
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
        "You are a helpful assistant.\n"
        "Output exactly this format:\n\n"
        "<<<BEGIN_PLAN>>>\n"
        "{plan_md}\n"
        "<<<END_PLAN>>>\n\n"
        "The task is about: {message_text}\n",
        encoding="utf-8"
    )

    monkeypatch.setenv("PROMPT_DIR", str(prompts))

    model_config = get_test_model_config("standard", temperature=0.0)
    
    # ---------- pipeline ----------
    prompt_agent = PromptAgent(AgentConfig(
        name="PromptAgent",
        model_config={
            "prompt_file": "prompt_agent.md",
            **model_config,
            # default_targets não é necessário neste teste pois o prompt já fixa o TARGET
        }
    ))

    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_bullets.md",  # baseline; será overriden para writer_paragraph.md
        model_config=model_config
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

    # 2) Verifica que o prompt do Writer foi override (deve ser diferente do original bullets)
    assert writer.config.prompt_file != "writer_bullets.md", f"Writer prompt_file should have been overridden, still: {writer.config.prompt_file}"
    
    # 3) Verifica que a troca de prompt funcionou - deve ter geração de texto mais longa (paragraph vs bullets)
    merged_text = "\n".join([t for t in finals if isinstance(t, str)])
    assert len(merged_text) > 50, f"Expected substantial output from paragraph writer, got: {len(merged_text)} chars"
    
    # 4) Verifica que usou o template paragraph (com marcadores) ao invés do template bullets
    assert "<<<BEGIN_PLAN>>>" in merged_text and "<<<END_PLAN>>>" in merged_text, "Expected paragraph template format with plan markers"