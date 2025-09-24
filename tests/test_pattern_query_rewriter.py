import os, pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.query_rewriter import QueryRewriterAgent
from tests.test_utils import skip_if_no_ollama, get_test_model_config

@skip_if_no_ollama()
def test_query_rewriter_ollama():
    model_config = get_test_model_config("standard", temperature=0.1)

    # Use existing prompt files from prompts/ directory

    # Rewriter - prompt_file should be in AgentConfig, not model_config
    rewriter = QueryRewriterAgent(AgentConfig(name="QueryRewriter", prompt_file="query_rewriter.md", model_config=model_config))

    # Answerer (só para garantir que continuamos usando LLMAgent no pipeline)
    answerer = LLMAgent(AgentConfig(name="Answerer", prompt_file="answer_with_context.md", model_config=model_config))

    agents = {"QueryRewriter": rewriter, "Answerer": answerer}
    graph  = {"QueryRewriter": ["Answerer"], "Answerer": []}
    wm = WorkflowManager(graph, agents)

    # Pergunta simples; sem contexto (contexts_md) por ser teste mínimo
    user_question = {"question": "Best way to measure funnel drop-offs in cross-platform analytics?", "hints_md": ""}

    results = wm.run_workflow("QueryRewriter", user_question)

    # Verifica que o rewriter produziu uma query reescrita não vazia
    # (não validamos conteúdo exato por ser LLM real)
    out_queries = [r.output.get("query") for r in results if isinstance(r.output, dict) and "query" in r.output]
    assert any(isinstance(q, str) and len(q.strip()) > 0 for q in out_queries), f"No valid queries found in outputs: {[r.output for r in results]}"
