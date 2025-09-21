import os
import pytest

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.fanout_agent import FanOutAgent
from src.agents.join_agent import JoinAgent


# ---- Skip se não houver Ollama configurado ----
ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason_ollama = "Set OLLAMA_MODEL (and optional OLLAMA_HOST) to run this test with real Ollama."

@pytest.mark.skipif(not ollama_model, reason=skip_reason_ollama)
def test_task4_parallelization_real_ollama(tmp_path, monkeypatch):
    """
    Teste do padrão Paralelização (FanOut/Join) usando Ollama real.
    - Cria prompts em diretório temporário e aponta PROMPT_DIR para lá.
    - Usa LLMAgent (default -> Ollama).
    """
    # Prompts temporários
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "tech_writer.md").write_text(
        "You are a senior software engineer.\n"
        "Produce a concise technical bullet list only.\n\nINPUT:\n{message_text}\n",
        encoding="utf-8"
    )
    (prompts_dir / "biz_writer.md").write_text(
        "You are a senior product manager.\n"
        "Produce a concise business/impact bullet list only.\n\nINPUT:\n{message_text}\n",
        encoding="utf-8"
    )
    (prompts_dir / "final_summarizer.md").write_text(
        "You will receive joined intermediate results as text.\n"
        "Write one short synthesis paragraph.\n\nJOINED INPUT:\n{message_text}\n",
        encoding="utf-8"
    )
    monkeypatch.setenv("PROMPT_DIR", str(prompts_dir))

    model_cfg = {"model": ollama_model, "options": {"temperature": 0.1}}

    tech_writer = LLMAgent(AgentConfig(name="TechWriter", prompt_file="tech_writer.md", model_config=model_cfg))
    biz_writer  = LLMAgent(AgentConfig(name="BizWriter",  prompt_file="biz_writer.md",  model_config=model_cfg))
    fanout = FanOutAgent(AgentConfig(name="FanOut", model_config={"branches": ["TechWriter", "BizWriter"]}))
    join = JoinAgent(AgentConfig(name="Join"))
    final = LLMAgent(AgentConfig(name="FinalSummary", prompt_file="final_summarizer.md", model_config=model_cfg))

    agents = {
        "FanOut": fanout,
        "TechWriter": tech_writer,
        "BizWriter": biz_writer,
        "Join": join,
        "FinalSummary": final
    }

    graph = {
        "FanOut": ["TechWriter", "BizWriter"],
        "TechWriter": ["Join"],
        "BizWriter":  ["Join"],
        "Join": ["FinalSummary"],
        "FinalSummary": []
    }

    wm = WorkflowManager(graph, agents)

    user_input = {"text": "Design an analytics feature to track user journeys on web and mobile."}
    results = wm.run_workflow("FanOut", user_input)

    # Verificações: deve haver saídas para TechWriter/BizWriter, Join e FinalSummary
    # (não verificamos conteúdo exato por ser LLM real)
    # Checa se alguma saída final contém texto.
    final_texts = [r.output.get("text") for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert any(t and isinstance(t, str) and len(t.strip()) > 0 for t in final_texts)
