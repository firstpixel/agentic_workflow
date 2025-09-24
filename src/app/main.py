import os
from src.agents.prompt_switcher import PromptSwitcherAgent, PromptAgent  # Unified agent
from src.agents.model_selector import ModelSelectorAgent  # Now we have the implementation
from src.agents.approval_gate import ApprovalGateAgent

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

from src.core.workflow_manager import WorkflowManager
from src.core.agent import AgentConfig, LLMAgent
from src.core.types import Result
from src.agents.switch_agent import SwitchAgent
from src.agents.critic_agent import CriticAgent
from src.core.utils import to_display  # <-- Add this import
from src.app.flows_tools import run_toolrunner_duckduckgo_demo

from src.app.flows_planner import demo_planner

# Add import for get_event_bus
from src.core.event_bus import get_event_bus

# NEW: retry/fallback demo flow
from src.app.flows import (
    make_prompt_handoff_flow,
    make_guardrails_writer_flow,
)
from src.app.flows_retries import run_retries_fallback_demo  # NEW


def demo_eventbus(auto_approve=False):
    """
    — EventBus + Settings
    Fase 1: ApprovalGate publica uma 'solicitação' no EventBus
    Subscriber simula a decisão humana e publica a decisão
    Fase 2: Rodamos o ApprovalGate com a decisão publicada
    """
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    bus = get_event_bus()

    approval = ApprovalGateAgent(AgentConfig(
        name="ApprovalGate",
        model_config={
            "summary_prompt_file": "approval_request.md",
            "next_on_approve": "Writer",
            "model": model,
            "options": {"temperature": 0.1}
        }
    ))
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config={"model": model, "options": {"temperature": 0.1}}
    ))
    agents = {"ApprovalGate": approval, "Writer": writer}
    graph  = {"ApprovalGate": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)

    # ---- Execução 1: solicita aprovação (PENDING) ----
    content = {"text": "Draft: Add cross-platform analytics pipeline for funnels and retention."}
    r1 = wm.run_workflow("ApprovalGate", content)
    pending = next((r for r in r1 if isinstance(r.output, dict) and r.output.get("status") == "PENDING"), None)
    if not pending:
        print("No PENDING approval (unexpected).")
        return
    approval_id = pending.output.get("approval_id", "")
    summary_md = pending.output.get("summary_md", "")

    # Publica evento de request
    bus.publish("approval.request", {
        "approval_id": approval_id,
        "summary_md": summary_md,
        "who": "ApprovalGate"
    })
    print(f"[bus] published approval.request for {approval_id}")

    # Simula ou solicita decisão humana
    if auto_approve:
        print(f"[bus] auto-approving for automated demo...")
        decision = {
            "approval_id": approval_id,
            "human_decision": "APPROVE",
            "human_comment": "Auto-approved for demo"
        }
    else:
        print("\n" + "="*60)
        print("🧑‍⚖️ EVENTBUS HUMAN APPROVAL REQUIRED")
        print("="*60)
        print("📋 SUMMARY FROM EVENTBUS:")
        print(summary_md)
        print("\n" + "-"*60)
        while True:
            print("\n🤔 Do you approve this EventBus request?")
            print("   1. APPROVE - Continue with the workflow")
            print("   2. REJECT - Stop the workflow")
            print("   3. Exit demo")
            choice = input("\nEnter your choice (1/2/3): ").strip()
            if choice == "1":
                human_decision = "APPROVE"
                human_comment = input("Optional comment (press Enter to skip): ").strip() or "Approved via EventBus"
                break
            elif choice == "2":
                human_decision = "REJECT"
                human_comment = input("Reason for rejection (press Enter to skip): ").strip() or "Rejected via EventBus"
                break
            elif choice == "3":
                print("👋 Exiting EventBus demo...")
                return
            else:
                print("❌ Invalid choice. Please enter 1, 2, or 3.")
        decision = {
            "approval_id": approval_id,
            "human_decision": human_decision,
            "human_comment": human_comment
        }
        print(f"[bus] human decided: {human_decision}")
    if not decision:
        print("[bus] no decision received (timeout).")
        return

    # ---- Execução 2: aplica decisão e segue para Writer ----
    r2 = wm.run_workflow("ApprovalGate", decision)
    print("\n=== TASK 13: EventBus Sample (HITL) ===")
    for r in r2:
        print("->", r.display_output or r.output)


def demo_flows_sample():
    """
    Demonstra dois helpers de fluxo:
      1) Prompt/Plan Handoff: PromptAgent -> Writer
      2) Guardrails -> Writer
    """
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")

    # 1) Prompt/Plan Handoff
    fb1 = make_prompt_handoff_flow(model=model)
    wm1 = fb1.manager()
    print("\n=== TASK 12: Prompt/Plan Handoff (flows.py) ===")
    r1 = wm1.run_workflow("PromptAgent", {
        "text": "Explain the API telemetry design. [[PARAGRAPH]]",
        "user_prompt": "Explain the API telemetry design. [[PARAGRAPH]]"
    })
    for r in r1:
        print("->", r.display_output or r.output)

    # 2) Guardrails -> Writer
    fb2 = make_guardrails_writer_flow(model=model)
    wm2 = fb2.manager()
    print("\n=== TASK 12: Guardrails -> Writer (flows.py) ===")
    r2 = wm2.run_workflow("Guardrails", {
        "text": "Contact me at jane@company.com. Summarize design.",
        "user_prompt": "Contact me at jane@company.com. Summarize design."
    })
    for r in r2:
        print("->", r.display_output or r.output)


def demo_display_unwrap():
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_paragraph.md",
        model_config={"model": model, "options": {"temperature": 0.0}}
    ))
    agents = {"Writer": writer}
    graph = {"Writer": []}
    wm = WorkflowManager(graph, agents)
    data = {"text": "Write a summary about user analytics features."}
    results = wm.run_workflow("Writer", data)
    print("\n=== Display/Unwrap Sample ===")
    for r in results:
        raw = r.output.get("text") if isinstance(r.output, dict) else r.output
        disp = r.display_output or to_display(None, raw)
        print("RAW:\n", raw, "\n---\nDISPLAY:\n", disp, "\n")


def demo_prompt_handoff():
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    prompt_agent = PromptAgent(AgentConfig(
        name="PromptAgent",
        model_config={
            "prompt_file": "prompt_agent.md",
            "model": model,
            "options": {"temperature": 0.0},
            "default_targets": {"Writer": "writer_bullets.md"}
        }
    ))
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_bullets.md",
        model_config={"model": model, "options": {"temperature": 0.1}}
    ))
    agents = {"PromptAgent": prompt_agent, "Writer": writer}
    graph  = {"PromptAgent": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)
    user_text = {"text": "Outline analytics pipeline design for funnels and retention. [[PARAGRAPH]]"}
    results = wm.run_workflow("PromptAgent", user_text)
    print("\n=== Prompt/Plan Handoff Sample ===")
    for r in results:
        print("->", r.display_output or r.output)
    print("Writer prompt_file (effective):", writer.config.prompt_file)


def demo_prompt_overrides():
    model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    switcher = PromptSwitcherAgent(AgentConfig(
        name="PromptSwitcher",
        model_config={
            "prompt_file": "prompt_switcher.md",
            "model": model,
            "options": {"temperature": 0.0},
            "default_targets": {"Writer": "writer_bullets.md"}
        }
    ))
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="writer_bullets.md",
        model_config={"model": model, "options": {"temperature": 0.1}}
    ))
    agents = {"PromptSwitcher": switcher, "Writer": writer}
    graph  = {"PromptSwitcher": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)
    user_text = {
        "text": "Outline the design choices for the API telemetry module. [[PARAGRAPH]]",
        "user_prompt": "Outline the design choices for the API telemetry module. [[PARAGRAPH]]"
    }
    results = wm.run_workflow("PromptSwitcher", user_text)
    print("\n=== TASK 10: Prompt Overrides Sample ===")
    for r in results:
        print("->", r.display_output or r.output)
    print("Writer prompt_file after routing:", writer.config.prompt_file)


def demo_model_routing():
    model1 = "llama3.2:1b"
    model2 = "llama3.2:3b"
    model3 = "gemma3:latest"
    router = ModelSelectorAgent(AgentConfig(
        name="ModelSelector",
        prompt_file="model_router.md",
        model_config={
            "model": model2,
            "options": {"temperature": 0.0},
            "classes": {
                "SIMPLE":   {"model": model1, "options": {"temperature": 0.1}},
                "STANDARD": {"model": model2, "options": {"temperature": 0.3}},
                "COMPLEX":  {"model": model3, "options": {"temperature": 0.6}}
            },
            "targets": ["Writer"]
        }
    ))
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config={"model": model1, "options": {"temperature": 0.0}}
    ))
    agents = {"ModelSelector": router, "Writer": writer}
    graph  = {"ModelSelector": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)

    print("\n=== Model Routing Sample (SIMPLE) ===")
    simple_result = wm.run_workflow("ModelSelector", {"text": "Write one sentence summary. [[SIMPLE]]"})
    for r in simple_result:
        print("->", r.display_output or r.output)
    print(f"✅ Writer model after SIMPLE: {writer.config.model_config}")

    writer.config.model_config = {"model": model1, "options": {"temperature": 0.0}}

    print("\n=== Model Routing Sample (STANDARD) ===")
    standard_result = wm.run_workflow("ModelSelector", {"text": "Analyze and explain the design patterns. [[STANDARD]]"})
    for r in standard_result:
        print("->", r.display_output or r.output)
    print(f"✅ Writer model after STANDARD: {writer.config.model_config}")

    writer.config.model_config = {"model": model1, "options": {"temperature": 0.0}}

    print("\n=== Model Routing Sample (COMPLEX) ===")
    complex_result = wm.run_workflow("ModelSelector", {"text": "[[COMPLEX]] Design microservices architecture"})
    for r in complex_result:
        print("->", r.display_output or r.output)
    print(f"✅ Writer model after COMPLEX: {writer.config.model_config}")

    print("\n🎯 Model routing complete! Each complexity level used different models:")
    print(f"   SIMPLE → {model1} (temp 0.1)")
    print(f"   STANDARD → {model2} (temp 0.3)")
    print(f"   COMPLEX → {model3} (temp 0.6)")


def demo_metrics_eval():
    model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    print(f"🔍 Checking Ollama availability for evaluation demo with model: {model}")
    ollama_available = check_ollama_availability(model)
    if not ollama_available:
        print("⚠️  Ollama not available - running only regex evaluation")
    else:
        print("✅ Ollama is available, proceeding with full evaluation demo...")

    model_cfg = {"model": model, "options": {"temperature": 0.1}}
    writer = LLMAgent(AgentConfig(name="Writer", prompt_file="tech_writer.md", model_config=model_cfg))
    agents = {"Writer": writer}
    graph  = {"Writer": []}
    metrics = MetricsCollector()
    wm = WorkflowManager(graph, agents, metrics=metrics)

    cases = [
        EvalCase(
            case_id="c1",
            entry_node="Writer",
            input_data={"text": "Design a telemetry module for API request timing and error rates."},
            required_regex=r"(api|request|error|telemetry)"
        )
    ]
    runner = EvaluationRunner(wm, metrics)
    results = runner.run(cases, judge="regex")
    print("\n=== Eval (regex) ===")
    for r in results:
        print(r)

    if ollama_available:
        judge_llm_cfg = {"model": model, "options": {"temperature": 0.1}}
        try:
            results_llm = runner.run(cases, judge="llm", llm_model_cfg=judge_llm_cfg, judge_prompt_file="eval_judge.md")
            print("\n=== Eval (LLM) ===")
            for r in results_llm:
                print(r)
        except Exception as e:
            print(f"\n⚠️  LLM evaluation failed: {str(e)}")
            print("   Continuing with regex evaluation only...")
    else:
        print("\n⚠️  Skipping LLM evaluation - Ollama not available")

    print("\n=== Metrics Summary ===")
    print(metrics.summary())
    print("\nCSV:\n", metrics.to_csv())


def demo_human_in_the_loop(auto_approve=False):
    model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}

    approval = ApprovalGateAgent(AgentConfig(
        name="ApprovalGate",
        model_config={
            "summary_prompt_file": "approval_request.md",
            "next_on_approve": "Writer",
            "model": model,
            "options": {"temperature": 0.1}
        }
    ))
    writer = LLMAgent(AgentConfig(name="Writer", prompt_file="tech_writer.md", model_config=model_cfg))
    agents = {"ApprovalGate": approval, "Writer": writer}
    graph  = {"ApprovalGate": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)

    content = {
        "text": "Draft: We will add a cross-platform analytics pipeline for funnels and retention.",
        "user_prompt": "Draft: We will add a cross-platform analytics pipeline for funnels and retention."
    }
    r1 = wm.run_workflow("ApprovalGate", content)
    print("\n=== HITL Sample – Request ===")
    for r in r1:
        print("->", r.display_output or r.output)

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

    print("\n" + "="*60)
    print("🧑‍⚖️ HUMAN APPROVAL REQUIRED")
    print("="*60)
    print("📋 SUMMARY:")
    print(summary_content)
    print("\n" + "-"*60)

    if auto_approve:
        print("\n🤖 Auto-approving for automated testing...")
        human_decision = "APPROVE"
        human_comment = "Auto-approved for demo"
    else:
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
        "human_comment": human_comment,
        "user_prompt": f"approval_id: {approval_id}, decision: {human_decision}, comment: {human_comment}"
    }

    print(f"\n=== HITL Sample – Decision ({human_decision}) ===")
    r2 = wm.run_workflow("ApprovalGate", decision_payload)
    for r in r2:
        print("->", r.display_output or r.output)


def demo_guardrails():
    model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}
    guard = GuardrailsAgent(AgentConfig(
        name="Guardrails",
        model_config={
            "pii_redact": True,
            "moderation_mode": "hybrid",
            "moderation_prompt_file": "moderation.md",
            "model": model,
            "options": {"temperature": 0.0}
        }
    ))
    writer = LLMAgent(AgentConfig(name="Writer", prompt_file="tech_writer.md", model_config=model_cfg))
    agents = {"Guardrails": guard, "Writer": writer}
    graph  = {"Guardrails": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)
    user_text = {"text": "My email is john.doe@example.com and phone +1 (555) 123-4567. Please outline the technical plan."}
    results = wm.run_workflow("Guardrails", user_text)
    print("\n=== Guardrails Sample ===")
    for r in results:
        print("->", r.display_output or r.output)


def demo_query_rewriter():
    model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}
    rewriter = QueryRewriterAgent(AgentConfig(name="QueryRewriter", prompt_file="query_rewriter.md", model_config=model_cfg))

    stm = MongoSTM()
    ltm = QdrantVectorStore(collection="agentic_docs")
    memory = MemoryManager(stm, ltm)
    retriever = RAGRetrieverAgent(AgentConfig(name="Retriever", model_config={"top_k":3}), memory)

    answer_model_cfg = {"model": model, "options": {"temperature": 0.1}}
    answerer = LLMAgent(AgentConfig(name="Answerer", prompt_file="answer_with_context.md", model_config=answer_model_cfg))

    agents = {"QueryRewriter": rewriter, "Retriever": retriever, "Answerer": answerer}
    graph = {"QueryRewriter": ["Retriever"], "Retriever": ["Answerer"], "Answerer": []}
    wm = WorkflowManager(graph, agents)

    user_question = {
        "question": "How do we track cross-platform user journeys for funnel analysis?",
        "hints_md": "- product: analytics\n- platforms: web, mobile\n- focus: funnel events"
    }
    results = wm.run_workflow("QueryRewriter", user_question)
    print("\n=== QueryRewriter Sample ===")
    for i, r in enumerate(results):
        print(f"Step {i+1}: ->", r.display_output or str(r.output)[:100] + "...")


def demo_rag_memory():
    model = os.getenv("OLLAMA_MODEL","llama3.2:1b")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}
    stm = MongoSTM()
    ltm = QdrantVectorStore(collection="agentic_docs")
    memory = MemoryManager(stm, ltm)

    memory.index_document("Our product tracks user journeys across web and mobile to identify friction points.", meta={"tag":"C1"})
    memory.index_document("Analytics events include page views, taps, and custom milestones with timestamps.", meta={"tag":"C2"})
    memory.index_document("Dashboards show funnels, retention curves, and cohort analysis.", meta={"tag":"C3"})

    session_id="demo-session"
    memory.stm_add(session_id,"user","How do we capture events for funnel analysis?")

    retriever = RAGRetrieverAgent(AgentConfig(name="Retriever", model_config={"top_k":3}), memory)
    answerer  = LLMAgent(AgentConfig(name="Answerer", prompt_file="answer_with_context.md", model_config=model_cfg))
    agents = {"Retriever": retriever, "Answerer": answerer}
    graph  = {"Retriever": ["Answerer"], "Answerer": []}
    wm = WorkflowManager(graph, agents)
    question = {"query": "How are analytics events captured for funnels?"}
    r1 = wm.run_workflow("Retriever", question)
    ctx_md = r1[-1].output.get("contexts_md","")
    # Build the user prompt by substituting the template manually
    question_text = "How are analytics events captured for funnels?"
    user_prompt = f"""Question: {question_text}

Retrieved Context:
{ctx_md}

Please answer concisely using only the information in the retrieved context."""
    r2 = wm.run_workflow("Answerer", {"user_prompt": user_prompt})

    print("\n=== RAG & Memory Sample ===")
    for r in r1+r2:
        print("->", r.display_output or r.output)


def demo_parallelization():
    os.environ["PROMPT_DIR"] = os.getenv("PROMPT_DIR", "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts")
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    model_cfg = {"model": model, "options": {"temperature": 0.1}}
    tech_writer = LLMAgent(AgentConfig(name="TechWriter", prompt_file="tech_writer.md", model_config=model_cfg))
    biz_writer  = LLMAgent(AgentConfig(name="BizWriter",  prompt_file="biz_writer.md",  model_config=model_cfg))
    fanout = FanOutAgent(AgentConfig(name="FanOut", model_config={"branches": ["TechWriter", "BizWriter"]}))
    join = JoinAgent(AgentConfig(name="Join"))
    final = LLMAgent(AgentConfig(name="FinalSummary", prompt_file="final_summarizer.md", model_config=model_cfg))
    agents = {"FanOut": fanout, "TechWriter": tech_writer, "BizWriter": biz_writer, "Join": join, "FinalSummary": final}
    graph = {"FanOut": ["TechWriter", "BizWriter"], "TechWriter": ["Join"], "BizWriter":  ["Join"], "Join": ["FinalSummary"], "FinalSummary": []}
    wm = WorkflowManager(graph, agents)
    user_input = {"text": "We plan to add a new analytics feature tracking user journeys across the mobile app and web."}
    results = wm.run_workflow("FanOut", user_input)
    print("\n=== Parallelization Sample ===")
    for r in results:
        print("->", r.display_output or r.output)


def create_ollama_llm_agent(model: str = "llama3.2:latest") -> 'LLMAgent':
    config = AgentConfig(name="OllamaLLM", model_config={"model": model, "options": {"temperature": 0.1}})
    return LLMAgent(config)


def check_ollama_availability(model: str = "llama3.2:latest", timeout: int = 5) -> bool:
    try:
        import ollama
        import httpx
        client = ollama.Client(timeout=timeout)
        client.chat(model=model, messages=[{"role": "user", "content": "test"}], stream=False)
        return True
    except ImportError:
        print("❌ Ollama library not available")
        return False
    except (Exception,) as e:
        print(f"❌ Ollama error: {str(e)}")
        return False


def demo_switch_agent_routing():
    print("=" * 60)
    print("🔀 SWITCH AGENT ROUTING DEMO")
    print("=" * 60)
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    print(f"🔍 Checking Ollama availability with model: {model}")
    if not check_ollama_availability(model):
        print("⚠️  Skipping Switch Agent demo - Ollama not available or model not found")
        return
    print("✅ Ollama is available, proceeding with demo...")
    llm_agent = create_ollama_llm_agent(model)
    routes_cfg = {
        "routes": {
            "Billing": {"keywords": ["boleto", "fatura", "cobrança"], "description": "Cobrança e pagamentos"},
            "Support": {"keywords": ["erro", "falha", "bug"],          "description": "Suporte técnico"},
            "Sales":   {"keywords": ["preço", "plano", "licença"],      "description": "Comercial/Vendas"}
        },
        "default": "Support",
        "mode": "hybrid",
        "confidence_threshold": 0.4,
        "model": model,
        "options": {"temperature": 0.0}
    }
    agents = {
        "Router":  SwitchAgent(AgentConfig(name="Router", prompt_file="switch_agent.md", model_config=routes_cfg)),
        "Billing": EchoAgent(AgentConfig(name="Billing")),
        "Support": EchoAgent(AgentConfig(name="Support")),
        "Sales":   EchoAgent(AgentConfig(name="Sales")),
    }
    graph = {"Router":  ["Billing", "Support", "Sales"], "Billing": [], "Support": [], "Sales": []}
    wm = WorkflowManager(graph, agents)
    print("\n=== Exemplo 1 ===")
    res1 = wm.run_workflow("Router", {"text": "Preciso gerar um boleto da minha fatura"})
    for r in res1:
        print("->", r.display_output or r.output)
    print("\n=== Exemplo 2 ===")
    res2 = wm.run_workflow("Router", {"text": "Estou com um erro 500 ao acessar a API"})
    for r in res2:
        print("->", r.display_output or r.output)
    print("\n=== Exemplo 3 ===")
    res3 = wm.run_workflow("Router", {"text": "Quais são os planos e preços disponíveis?"})
    for r in res3:
        print("->", r.display_output or r.output)


def demo_critic_agent_evaluation():
    print("\n" + "=" * 60)
    print("🧪 CRITIC AGENT EVALUATION DEMO")
    print("=" * 60)
    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    if not check_ollama_availability(model):
        print("⚠️  Skipping Critic Agent demo - Ollama not available or model not found")
        return
    print("✅ Ollama is available, proceeding with demo...")
    llm_agent = create_ollama_llm_agent(model)
    os.environ['PROMPT_DIR'] = os.getenv('PROMPT_DIR', "/Users/gilbeyruth/AIProjects/agentic_workflow/prompts")

    writer = LLMAgent(AgentConfig(name="Writer", model_config={"model": model}, prompt_file="tech_writer.md"))
    critic = CriticAgent(AgentConfig(
        name="Critic",
        model_config={
            "rubric": ["Clarity and structure", "Technical accuracy", "Completeness"],
            "threshold": 7.0,
            "max_iters": 2,
            "next_on_pass": "Done",
            "model": model
        },
        prompt_file="critic_agent.md"
    ))

    class DoneAgent(EchoAgent):
        def run(self, message):
            return Result.ok(output={"done": True, "final_content": message.data},
                             display_output="✅ Content approved and workflow complete!")

    done = DoneAgent(AgentConfig(name="Done"))
    agents = {"Writer": writer, "Critic": critic, "Done": done}
    graph = {"Writer": ["Critic"], "Critic": ["Writer", "Done"], "Done": []}
    wm = WorkflowManager(graph, agents)

    print("\n=== Writer-Critic Feedback Loop Example ===")
    prompt = "Write a technical summary about Python async/await patterns. Include examples and best practices."
    try:
        results = wm.run_workflow("Writer", {"user_prompt": prompt})
        print(f"\n📊 Workflow completed with {len(results)} steps:")
        for i, r in enumerate(results):
            agent_name = r.metrics.get("agent", "Unknown")
            print(f"  Step {i+1} ({agent_name}): {r.display_output or str(r.output)[:100]}")
        if any("approved and workflow complete" in (r.display_output or "") for r in results):
            print("\n🎉 Content was approved by the critic!")
        else:
            print("\n⚠️  Content may need more iterations or workflow was incomplete.")
    except Exception as e:
        print(f"\n❌ Error in critic workflow: {e}")


# NEW: Retry/Fallback demo wrapper
def demo_retries_and_fallbacks():
    run_retries_fallback_demo()


def main():
    print("🚀 Running Agentic Workflow Examples\n")

    run_toolrunner_duckduckgo_demo()
    demo_retries_and_fallbacks()
    demo_switch_agent_routing()
    demo_critic_agent_evaluation()
    demo_parallelization()
    demo_rag_memory()
    demo_query_rewriter()
    demo_guardrails()
    demo_human_in_the_loop(auto_approve=True)
    demo_metrics_eval()
    demo_model_routing()
    demo_prompt_overrides()
    demo_display_unwrap()
    demo_flows_sample()
    demo_planner()

    demo_planner_coder_integration()


def demo_planner_coder_integration():

    """
    Demonstrate the CodeExecutorAgent with PlannerFlow
    Creates actual files and executes code based on planning
    """
    print("\n🚀 Testing CodeExecutorAgent with PlannerFlow")
    print("=" * 60)
    
    try:
        from src.app.flow_planner_coder import demo_planner_coder
        # Run a simple demo
        demo_planner_coder(
            "Create a Python hello world script with proper documentation",
            "hello_world_demo"
        )
        print("✅ CodeExecutorAgent demo completed successfully!")
    except Exception as e:
        print(f"❌ CodeExecutorAgent demo failed: {e}")
        print("Note: This demo requires the CodeExecutorAgent to be properly configured")


def demo_eventbus_interactive():
    print("🚀 Testing Interactive EventBus Human Approval\n")
    demo_eventbus(auto_approve=False)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--hitl":
        demo_eventbus_interactive()
    else:
        main()
