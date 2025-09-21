import os
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

    print("\n=== TASK 4: Parallelization Sample ===")
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


def main():
    print("🚀 Running Agentic Workflow Examples\n")
    
    # Run SwitchAgent routing examples
    demo_switch_agent_routing()
    
    # Run CriticAgent evaluation examples  
    demo_critic_agent_evaluation()
    
    
    demo_parallelization()


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


if __name__ == "__main__":
    main()

