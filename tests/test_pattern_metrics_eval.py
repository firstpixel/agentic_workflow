import os, pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.eval.metrics import MetricsCollector
from src.eval.evaluation import EvaluationRunner, EvalCase

ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason = "Set OLLAMA_MODEL (and optional OLLAMA_HOST) to run this test with real Ollama."

@pytest.mark.skipif(not ollama_model, reason=skip_reason)
def test_task8_metrics_and_eval_with_ollama(tmp_path, monkeypatch):
    # --- prompts em arquivos ---
    prompts = tmp_path / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    # Prompt do writer (carregado via prompt_file)
    (prompts / "tech_writer.md").write_text(
        "You are a senior software engineer.\n"
        "Produce a concise technical bullet list only.\n\nINPUT:\n{message_text}\n",
        encoding="utf-8"
    )
    # Prompt do juiz de avaliação (carregado via prompt_file no runner)
    (prompts / "eval_judge.md").write_text(
        "You are a reliable evaluation judge.\n\n"
        "### CASE\n{case_md}\n\n"
        "### MODEL OUTPUT\n{model_output_md}\n\n"
        "### DECISION RULES\n- PASS if output mentions API and telemetry\n\n"
        "### OUTPUT\n"
        "### VERDICT\nPASS\n\n"
        "### REASONS\n- mentions API and telemetry\n",
        encoding="utf-8"
    )
    monkeypatch.setenv("PROMPT_DIR", str(prompts))

    # --- pipeline ---
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config={"model": ollama_model, "options": {"temperature": 0.1}}
    ))
    agents = {"Writer": writer}
    graph  = {"Writer": []}

    metrics = MetricsCollector()
    wm = WorkflowManager(graph, agents, metrics=metrics)

    # Caso de avaliação
    cases = [
        EvalCase(
            case_id="case_api_tel",
            entry_node="Writer",
            input_data={"text": "Design a telemetry module for API request timing and error rates."},
            required_regex=r"(api|telemetry)"
        )
    ]
    runner = EvaluationRunner(wm, metrics)

    # 1) regex judge (determinístico)
    res = runner.run(cases, judge="regex")
    assert res and res[0]["verdict"] in ("PASS","FAIL")

    # 2) llm judge (usa prompt eval_judge.md do PROMPT_DIR)
    res_llm = runner.run(cases, judge="llm", llm_model_cfg={"model": ollama_model, "options":{"temperature":0.1}}, judge_prompt_file="eval_judge.md")
    assert res_llm and res_llm[0]["verdict"] in ("PASS","FAIL")

    # métricas coletadas
    summ = metrics.summary()
    assert summ["total_nodes"] >= 1
    assert "avg_latency_sec" in summ
