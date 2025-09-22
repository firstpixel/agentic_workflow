import os
# from agents.model_router import ModelRouterAgent  # TODO: Implement ModelRouterAgent
from src.agents.approval_gate import ApprovalGateAgent
from src.core.workflow_manager import WorkflowManager
from src.core.agent import AgentConfig
from src.agents.echo import EchoAgent

# def main():
#     agents = {
#         "Start": EchoAgent(AgentConfig(name="Start")),
#         "Then":  EchoAgent(AgentConfig(name="Then")),
#     }
#     graph = {
#         "Start": ["Then"],
#         "Then":  []
#     }
#     wm = WorkflowManager(graph, agents)
#     results = wm.run_workflow("Start", {"msg": "hello"})
#     for r in results:
#         print(r.success, r.output)

# if __name__ == "__main__":
#     main()


from src.core.workflow_manager import WorkflowManager
from src.core.agent import AgentConfig, LLMAgent
from src.core.types import Result
from src.agents.switch_agent import SwitchAgent
from src.agents.critic_agent import CriticAgent

# Um agente de eco simples para visualizar para onde roteamos
from src.agents.echo import EchoAgent  # use o echo do exemplo do Task 1 (ou crie agora)
from src.agents.fanout_agent import FanOutAgent
from src.agents.join_agent import JoinAgent

from src.memory import MongoSTM, QdrantVectorStore, MemoryManager
from src.agents.rag_retriever import RAGRetrieverAgent
from src.agents.query_rewriter import QueryRewriterAgent
from src.agents.guardrails_agent import GuardrailsAgent
from src.eval.metrics import MetricsCollector  # <-- Add this import
from src.eval.evaluation import EvalCase, EvaluationRunner  # <-- Add this import


# TODO: Implement ModelRouterAgent first
# def demo_model_routing():
#     """
#     Router -> Writer
#     The router classifies and overrides Writer's model_config (e.g., temperature) per class.
#     """
#     model = os.getenv("OLLAMA_MODEL", "llama3")
# 
#     router = ModelRouterAgent(AgentConfig(
#         name="ModelRouter",
#         model_config={
#             "prompt_file": "model_router.md",
#             "model": model,
#             "options": {"temperature": 0.0},
#             "classes": {
#                 "SIMPLE":   {"model": model, "options": {"temperature": 0.1}},
#                 "STANDARD": {"model": model, "options": {"temperature": 0.3}},
#                 "COMPLEX":  {"model": model, "options": {"temperature": 0.6}}
#             },
#             "targets": ["Writer"]
#         }
#     ))
# 
#     writer = LLMAgent(AgentConfig(
#         name="Writer",
#         prompt_file="tech_writer.md",
#         model_config={"model": model, "options": {"temperature": 0.4}}  # baseline; will be overridden
#     ))
# 
#     agents = {"ModelRouter": router, "Writer": writer}
#     graph  = {"ModelRouter": ["Writer"], "Writer": []}
# 
#     wm = WorkflowManager(graph, agents)
# 
#     user_text = {"text": "Create a quick summary for the API design. [[SIMPLE]]"}
#     results = wm.run_workflow("ModelRouter", user_text)
# 
#     print("\n=== TASK 9: Model Routing Sample ===")
#     for r in results:
#         print("->", r.display_output or r.output)
# 
#     # Show the effective writer config after routing (should reflect SIMPLE override)
#     print("Writer model_config after routing:", writer.config.model_config)


def demo_metrics_eval():
    """
    Exemplo: Writer -> (final) com métricas + avaliação.
    - Prompt do Writer carregado de arquivo .md (tech_writer.md).
    - Juiz por regex (determinístico) e exemplo de juiz LLM (eval_judge.md).
    """
    model = os.getenv("OLLAMA_MODEL", "llama3")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}

    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config=model_cfg
    ))

    agents = {"Writer": writer}
    graph  = {"Writer": []}

    metrics = MetricsCollector()
    wm = WorkflowManager(graph, agents, metrics=metrics)

    # Executa um caso simples
    cases = [
        EvalCase(
            case_id="c1",
            entry_node="Writer",
            input_data={"text": "Design a telemetry module for API request timing and error rates."},
            required_regex=r"(api|request|error|telemetry)"
        )
    ]
    runner = EvaluationRunner(wm, metrics)

    # Julgamento determinístico (regex)
    results = runner.run(cases, judge="regex")
    print("\n=== Eval (regex) ===")
    for r in results:
        print(r)

    # (Opcional) Juiz LLM com prompt .md (eval_judge.md)
    judge_llm_cfg = {"model": model, "options": {"temperature": 0.1}}
    results_llm = runner.run(cases, judge="llm", llm_model_cfg=judge_llm_cfg, judge_prompt_file="eval_judge.md")
    print("\n=== Eval (LLM) ===")
    for r in results_llm:
        print(r)

    print("\n=== Metrics Summary ===")
    print(metrics.summary())
    print("\nCSV:\n", metrics.to_csv())

def demo_human_in_the_loop():
    """
    Padrão HITL em duas chamadas:
      1) ApprovalGate (request) -> HALT com resumo para humano
      2) ApprovalGate (decision=APPROVE) -> segue para Writer
    """
    model = os.getenv("OLLAMA_MODEL", "llama3")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}

    # Gate de aprovação
    approval = ApprovalGateAgent(AgentConfig(
        name="ApprovalGate",
        model_config={
            "summary_prompt_file": "approval_request.md",
            "next_on_approve": "Writer",
            "next_on_reject": "Rework",    # opcional
            "model": model,
            "options": {"temperature": 0.1}
        }
    ))

    # Writer (pós-aprovação) – usa prompt .md existente; por ex., tech_writer.md
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config=model_cfg
    ))

    agents = {"ApprovalGate": approval, "Writer": writer}
    graph  = {"ApprovalGate": ["Writer"], "Writer": []}

    wm = WorkflowManager(graph, agents)

    # ---- Execução 1: solicita aprovação (HALT) ----
    content = {
        "text": "Draft: We will add a cross-platform analytics pipeline for funnels and retention."
    }
    r1 = wm.run_workflow("ApprovalGate", content)
    print("\n=== HITL Sample – Request ===")
    for r in r1:
        print("->", r.display_output or r.output)

    # Get the approval_id from the pending request
    approval_id = ""
    summary_content = ""
    for r in r1[::-1]:
        if isinstance(r.output, dict) and r.output.get("status") == "PENDING":
            approval_id = r.output.get("approval_id","")
            summary_content = r.output.get("summary_md", "")
            break

    if not approval_id:
        print("❌ No approval_id found in workflow results")
        return

    # Display the summary for human review
    print("\n" + "="*60)
    print("🧑‍⚖️ HUMAN APPROVAL REQUIRED")
    print("="*60)
    print("📋 SUMMARY:")
    print(summary_content)
    print("\n" + "-"*60)
    
    # Prompt user for decision
    while True:
        print("\n🤔 Do you approve this request?")
        print("   1. APPROVE - Continue with the writer")
        print("   2. REJECT - Stop the workflow")
        print("   3. Exit demo")
        
        choice = input("\nEnter your choice (1/2/3): ").strip()
        
        if choice == "1":
            human_decision = "APPROVE"
            human_comment = input("Optional comment (press Enter to skip): ").strip() or "Approved by user"
            break
        elif choice == "2":
            human_decision = "REJECT"
            human_comment = input("Reason for rejection (press Enter to skip): ").strip() or "Rejected by user"
            break
        elif choice == "3":
            print("👋 Exiting HITL demo...")
            return
        else:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")

    decision_payload = {
        "approval_id": approval_id,
        "human_decision": human_decision,
        "human_comment": human_comment
    }

    # ---- Execução 2: aplica decisão e segue para Writer ----
    print(f"\n=== HITL Sample – Decision ({human_decision}) ===")
    r2 = wm.run_workflow("ApprovalGate", decision_payload)
    for r in r2:
        print("->", r.display_output or r.output)

def demo_guardrails():
    model = os.getenv("OLLAMA_MODEL", "llama3")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}

    guard = GuardrailsAgent(AgentConfig(
        name="Guardrails",
        model_config={
            "pii_redact": True,
            "moderation_mode": "hybrid",           # "deterministic" | "llm" | "hybrid"
            "moderation_prompt_file": "moderation.md",
            "model": model,
            "options": {"temperature": 0.0}
        }
    ))

    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",             # reusa seu prompt de Task 4
        model_config=model_cfg
    ))

    agents = {"Guardrails": guard, "Writer": writer}
    graph  = {"Guardrails": ["Writer"], "Writer": []}

    wm = WorkflowManager(graph, agents)

    user_text = {
        "text": "My email is john.doe@example.com and phone +1 (555) 123-4567. Please outline the technical plan."
    }
    results = wm.run_workflow("Guardrails", user_text)

    print("\n=== Guardrails Sample ===")
    for r in results:
        print("->", r.display_output or r.output)

def demo_query_rewriter():
    """
    Sample do QueryRewriter em fluxo:
    QueryRewriter -> (Retriever) -> Answerer
    """
    model = os.getenv("OLLAMA_MODEL", "llama3")
    model_cfg = {"model": model, "options": {"temperature": 0.1}, "prompt_file": "query_rewriter.md"}

    # Rewriter (usa prompt .md)
    rewriter = QueryRewriterAgent(AgentConfig(name="QueryRewriter", model_config=model_cfg))

    # Se quiser ligar o pipeline completo com RAG (ajuste seus imports conforme sua base):
    stm = MongoSTM()
    ltm = QdrantVectorStore(collection="agentic_docs")
    memory = MemoryManager(stm, ltm)
    retriever = RAGRetrieverAgent(AgentConfig(name="Retriever", model_config={"top_k":3}), memory)

    # Answerer com prompt de contexto (já usado no Task 5)
    answer_model_cfg = {"model": model, "options": {"temperature": 0.1}}
    answerer = LLMAgent(AgentConfig(name="Answerer", prompt_file="answer_with_context.md", model_config=answer_model_cfg))

    agents = {
        "QueryRewriter": rewriter,
        "Retriever": retriever,
        "Answerer": answerer
    }

    # Grafo completo: Rewriter -> Retriever -> Answerer
    graph = {
        "QueryRewriter": ["Retriever"],
        "Retriever": ["Answerer"],
        "Answerer": []
    }

    wm = WorkflowManager(graph, agents)

    user_question = {
        "question": "How do we track cross-platform user journeys for funnel analysis?",
        "hints_md": "- product: analytics\n- platforms: web, mobile\n- focus: funnel events"
    }

    # Exec: the workflow now properly chains Rewriter -> Retriever -> Answerer
    # We need to ensure the original question is preserved for the Answerer
    results = wm.run_workflow("QueryRewriter", user_question)

    print("\n=== QueryRewriter Sample ===")
    for i, r in enumerate(results):
        print(f"Step {i+1}: ->", r.display_output or str(r.output)[:100] + "...")

def demo_rag_memory():
    """
    Indexa alguns documentos no Qdrant, grava STM no Mongo,
    recupera contexto e responde com base no prompt markdown.
    Requer:
      - QDRANT_URL
      - MONGODB_URI
      - OLLAMA_MODEL (e opcional OLLAMA_HOST)
    """
    model = os.getenv("OLLAMA_MODEL","llama3")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}

    # --- Memória: STM (Mongo) + LTM/RAG (Qdrant)
    stm = MongoSTM()  # usa MONGODB_URI
    ltm = QdrantVectorStore(collection="agentic_docs")
    memory = MemoryManager(stm, ltm)

    # Indexação de exemplo
    memory.index_document("Our product tracks user journeys across web and mobile to identify friction points.", meta={"tag":"C1"})
    memory.index_document("Analytics events include page views, taps, and custom milestones with timestamps.", meta={"tag":"C2"})
    memory.index_document("Dashboards show funnels, retention curves, and cohort analysis.", meta={"tag":"C3"})

    session_id="demo-session"
    memory.stm_add(session_id,"user","How do we capture events for funnel analysis?")

    # --- Agentes
    retriever = RAGRetrieverAgent(AgentConfig(name="Retriever", model_config={"top_k":3}), memory)
    answerer  = LLMAgent(AgentConfig(name="Answerer", prompt_file="answer_with_context.md", model_config=model_cfg))

    agents = {"Retriever": retriever, "Answerer": answerer}
    graph  = {"Retriever": ["Answerer"], "Answerer": []}

    wm = WorkflowManager(graph, agents)

    # A pergunta entra e vira {question} no prompt do Answerer
    question = {"query": "How are analytics events captured for funnels?"}
    # EXEC 1: Retriever
    r1 = wm.run_workflow("Retriever", question)
    # Pega contexts_md do último result do Retriever
    ctx_md = r1[-1].output.get("contexts_md","")

    # EXEC 2: Answerer usando o contexto recuperado
    r2 = wm.run_workflow("Answerer", {"question":"How are analytics events captured for funnels?", "contexts_md": ctx_md})

    print("\n=== RAG & Memory Sample ===")
    for r in r1+r2:
        print("->", r.display_output or r.output)

def demo_parallelization():
    """
    FanOut -> (TechWriter, BizWriter) -> Join -> Final
    Usa LLMAgent com Ollama e prompts .md (sem mock).
    """
    # Set the prompts directory to our actual prompts folder
    os.environ["PROMPT_DIR"] = "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts"
    
    # Config básico do modelo Ollama - use a more capable model
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}

    # Agentes de ramo (cada um com seu prompt .md)
    tech_writer = LLMAgent(AgentConfig(name="TechWriter", prompt_file="tech_writer.md", model_config=model_cfg))
    biz_writer  = LLMAgent(AgentConfig(name="BizWriter",  prompt_file="biz_writer.md",  model_config=model_cfg))

    # FanOut (define os ramos)
    fanout = FanOutAgent(AgentConfig(
        name="FanOut",
        model_config={"branches": ["TechWriter", "BizWriter"]}
    ))

    # Join (agrega)
    join = JoinAgent(AgentConfig(name="Join"))

    # Sumarizador final (usa o texto joined como {message_text})
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

    user_input = {
        "text": "We plan to add a new analytics feature tracking user journeys across the mobile app and web."
    }
    results = wm.run_workflow("FanOut", user_input)

    print("\n=== Parallelization Sample ===")
    for r in results:
        print("->", r.display_output or r.output)

def create_ollama_llm_agent(model: str = "llama3.2:latest") -> 'LLMAgent':
    """Create LLMAgent that uses real Ollama (no custom llm_fn, uses default)"""
    config = AgentConfig(
        name="OllamaLLM",
        model_config={
            "model": model,
            "options": {"temperature": 0.1}
        }
    )
    # Don't pass llm_fn - let it use the default Ollama integration
    return LLMAgent(config)


def check_ollama_availability(model: str = "llama3.2:latest", timeout: int = 5) -> bool:
    """Check if Ollama is available and the model is accessible."""
    try:
        import ollama
        import httpx
        
        client = ollama.Client(timeout=timeout)
        # Try a simple test with the model
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": "test"}],
            stream=False
        )
        return True
    except ImportError:
        print("❌ Ollama library not available")
        return False
    except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout):
        print(f"⏰ Ollama server timeout after {timeout}s - server may not be running")
        return False
    except Exception as e:
        print(f"❌ Ollama error: {str(e)}")
        return False





def demo_switch_agent_routing():
    """Demonstrates SwitchAgent routing capabilities."""
    print("=" * 60)
    print("🔀 SWITCH AGENT ROUTING DEMO")
    print("=" * 60)
    
    # Use more capable model for complex JSON tasks
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    
    print(f"🔍 Checking Ollama availability with model: {model}")
    if not check_ollama_availability(model):
        print("⚠️  Skipping Switch Agent demo - Ollama not available or model not found")
        print("   Set OLLAMA_MODEL environment variable or ensure Ollama is running")
        return
    
    print("✅ Ollama is available, proceeding with demo...")
    
    # Create LLMAgent with Ollama integration
    llm_agent = create_ollama_llm_agent(model)
    
    # --- Defina rotas do SwitchAgent ---
    routes_cfg = {
        "routes": {
            "Billing": {"keywords": ["boleto", "fatura", "cobrança"], "description": "Cobrança e pagamentos"},
            "Support": {"keywords": ["erro", "falha", "bug"],          "description": "Suporte técnico"},
            "Sales":   {"keywords": ["preço", "plano", "licença"],      "description": "Comercial/Vendas"}
        },
        "default": "Support",
        "mode": "hybrid",                 # "llm" | "keywords" | "hybrid"
        "confidence_threshold": 0.4,     # Lowered to accept more LLM decisions
        "model": model                    # Use the same model as availability check
    }

    agents = {
        "Router":  SwitchAgent(AgentConfig(name="Router", model_config=routes_cfg), llm_fn=llm_agent.llm_fn),
        "Billing": EchoAgent(AgentConfig(name="Billing")),
        "Support": EchoAgent(AgentConfig(name="Support")),
        "Sales":   EchoAgent(AgentConfig(name="Sales")),
    }

    # O grafo lista possíveis próximos do Router.
    # O SwitchAgent vai escolher UM com control.goto.
    graph = {
        "Router":  ["Billing", "Support", "Sales"],
        "Billing": [],
        "Support": [],
        "Sales":   []
    }

    wm = WorkflowManager(graph, agents)

    # Exemplo 1: deveria cair em Billing (keywords)
    print("\n=== Exemplo 1 ===")
    res1 = wm.run_workflow("Router", {"text": "Preciso gerar um boleto da minha fatura"})
    for r in res1:
        print("->", r.display_output or r.output)

    # Exemplo 2: deveria cair em Support
    print("\n=== Exemplo 2 ===")
    res2 = wm.run_workflow("Router", {"text": "Estou com um erro 500 ao acessar a API"})
    for r in res2:
        print("->", r.display_output or r.output)

    # Exemplo 3: deveria cair em Sales
    print("\n=== Exemplo 3 ===")
    res3 = wm.run_workflow("Router", {"text": "Quais são os planos e preços disponíveis?"})
    for r in res3:
        print("->", r.display_output or r.output)


def demo_critic_agent_evaluation():
    """Demonstrates CriticAgent evaluation and feedback loop capabilities."""
    print("\n" + "=" * 60)
    print("🧪 CRITIC AGENT EVALUATION DEMO")
    print("=" * 60)
    
    # Use more capable model for complex JSON tasks
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    
    print(f"🔍 Checking Ollama availability with model: {model}")
    if not check_ollama_availability(model):
        print("⚠️  Skipping Critic Agent demo - Ollama not available or model not found")
        print("   Set OLLAMA_MODEL environment variable or ensure Ollama is running")
        return
    
    print("✅ Ollama is available, proceeding with demo...")
    
    # Create LLMAgent with Ollama integration
    llm_agent = create_ollama_llm_agent(model)
    
    # Use the actual prompts directory with our real critic_agent.md file
    os.environ['PROMPT_DIR'] = "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts"
    
    # Create agents for writer-critic workflow
    writer = LLMAgent(
        AgentConfig(
            name="Writer", 
            model_config={"model": model}
        ), 
        llm_fn=llm_agent.llm_fn
    )
    
    critic = CriticAgent(
        AgentConfig(
            name="Critic",
            model_config={
                "rubric": ["Clarity and structure", "Technical accuracy", "Completeness"],
                "threshold": 7.0,
                "max_iters": 2,
                "next_on_pass": "Done",
                "prompt_file": "critic_agent.md",
                "model": model
            }
        ),
        llm_fn=llm_agent.llm_fn
    )
    
    # Simple "Done" agent 
    class DoneAgent(EchoAgent):
        def run(self, message):
            return Result.ok(
                output={"done": True, "final_content": message.data},
                display_output="✅ Content approved and workflow complete!"
            )
    
    done = DoneAgent(AgentConfig(name="Done"))

    agents = {"Writer": writer, "Critic": critic, "Done": done}
    
    # Graph: Writer -> Critic -> (repeat to Writer OR goto Done)
    graph = {
        "Writer": ["Critic"], 
        "Critic": ["Writer", "Done"], 
        "Done": []
    }

    wm = WorkflowManager(graph, agents)

    # Example 1: Ask writer to create content, then critic evaluates
    print("\n=== Writer-Critic Feedback Loop Example ===")
    prompt = "Write a technical summary about Python async/await patterns. Include examples and best practices."
    
    try:
        results = wm.run_workflow("Writer", {"prompt": prompt})
        
        print(f"\n📊 Workflow completed with {len(results)} steps:")
        for i, r in enumerate(results):
            agent_name = r.metrics.get("agent", "Unknown")
            print(f"  Step {i+1} ({agent_name}): {r.display_output or str(r.output)[:100]}")
            
        # Check if we reached the Done agent
        if any("approved and workflow complete" in (r.display_output or "") for r in results):
            print("\n🎉 Content was approved by the critic!")
        else:
            print("\n⚠️  Content may need more iterations or workflow was incomplete.")
            
    except Exception as e:
        print(f"\n❌ Error in critic workflow: {e}")
        
def main():
    print("🚀 Running Agentic Workflow Examples\n")
    
    # Run SwitchAgent routing examples
    demo_switch_agent_routing()
    
    # Run CriticAgent evaluation examples  
    demo_critic_agent_evaluation()
    
    demo_parallelization()

    demo_rag_memory()

    demo_query_rewriter()
    
    demo_guardrails()
    
    demo_human_in_the_loop()

    demo_metrics_eval()

    # demo_model_routing()  # TODO: Implement ModelRouterAgent first


if __name__ == "__main__":
    main()

