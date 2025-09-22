import os, pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.query_rewriter import QueryRewriterAgent


ollama_model = os.getenv("OLLAMA_MODEL", "")
skip_reason = "Set OLLAMA_MODEL (and optional OLLAMA_HOST) to run this test with real Ollama."

@pytest.mark.skipif(not ollama_model, reason=skip_reason)
def test_query_rewriter_ollama():
    # Use existing prompt files from prompts/ directory

    # Rewriter
    rewriter_cfg = {"model": ollama_model, "options": {"temperature": 0.1}, "prompt_file": "query_rewriter.md"}
    rewriter = QueryRewriterAgent(AgentConfig(name="QueryRewriter", model_config=rewriter_cfg))

    # Answerer (só para garantir que continuamos usando LLMAgent no pipeline)
    answer_cfg = {"model": ollama_model, "options": {"temperature": 0.1}}
    answerer = LLMAgent(AgentConfig(name="Answerer", prompt_file="answer_with_context.md", model_config=answer_cfg))

    agents = {"QueryRewriter": rewriter, "Answerer": answerer}
    graph  = {"QueryRewriter": ["Answerer"], "Answerer": []}
    wm = WorkflowManager(graph, agents)

    # Pergunta simples; sem contexto (contexts_md) por ser teste mínimo
    user_question = {"question": "Best way to measure funnel drop-offs in cross-platform analytics?", "hints_md": ""}

    results = wm.run_workflow("QueryRewriter", user_question)

    # Verifica que o rewriter produziu uma query reescrita não vazia
    # (não validamos conteúdo exato por ser LLM real)
    out_queries = [r.output.get("query") for r in results if isinstance(r.output, dict) and "query" in r.output]
    assert any(isinstance(q, str) and len(q.strip()) > 0 for q in out_queries)
