import os
import pytest

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.fanout_agent import FanOutAgent
from src.agents.join_agent import JoinAgent
from tests.test_utils import skip_if_no_ollama, get_test_model_config


@skip_if_no_ollama()
def test_task4_parallelization_real_ollama():
    """
    Teste do padrão Paralelização (FanOut/Join) usando Ollama real.
    - Uses existing prompt files from prompts/ directory.
    - Uses LLMAgent (default -> Ollama).
    """

    model_cfg = get_test_model_config("standard", temperature=0.1)

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
