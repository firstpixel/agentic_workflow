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


def create_ollama_llm_fn(model: str = "llama3.2:latest"):
    """Create an Ollama LLM function for use with agents."""
    def ollama_llm(prompt: str, **kwargs) -> str:
        try:
            import ollama
            
            # Override model if specified in kwargs
            model_to_use = kwargs.get("model", model)
            
            # Create the chat messages
            messages = [{"role": "user", "content": prompt}]
            
            # Call Ollama
            response = ollama.chat(
                model=model_to_use,
                messages=messages,
                stream=False
            )
            
            return response["message"]["content"]
            
        except ImportError:
            return f"[OLLAMA NOT AVAILABLE] {prompt[:120]}"
        except Exception as e:
            return f"[OLLAMA ERROR: {str(e)}] {prompt[:120]}"
    
    return ollama_llm


def main():
    print("🚀 Running Agentic Workflow Examples\n")
    
    # Run SwitchAgent routing examples
    demo_switch_agent_routing()
    
    # Run CriticAgent evaluation examples  
    demo_critic_agent_evaluation()


def demo_switch_agent_routing():
    """Demonstrates SwitchAgent routing capabilities."""
    print("=" * 60)
    print("🔀 SWITCH AGENT ROUTING DEMO")
    print("=" * 60)
    
    # Create Ollama LLM function
    ollama_llm = create_ollama_llm_fn("llama3.2:latest")
    
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
        "model": "llama3.2:latest"        # Add model specification
    }

    agents = {
        "Router":  SwitchAgent(AgentConfig(name="Router", model_config=routes_cfg), llm_fn=ollama_llm),
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
    
    # Create Ollama LLM function
    ollama_llm = create_ollama_llm_fn("llama3.2:latest")
    
    # Create a simple prompt file in memory (for demo purposes)
    import tempfile
    import os
    
    # Setup temporary prompt directory
    tmp_dir = tempfile.mkdtemp()
    prompt_file = f'{tmp_dir}/critic_agent.md'
    with open(prompt_file, 'w') as f:
        f.write('''You are a meticulous content reviewer and evaluator.

Evaluate the following text based on the provided rubric criteria.
Return ONLY a JSON response with the following format:
{{"score": <overall_score_0_to_10>, "rubric_scores": {{"criteria1": <score>, "criteria2": <score>}}, "reasons": ["reason1", "reason2"]}}

EVALUATION RUBRIC:
{rubric_json}

TEXT TO EVALUATE:
{text}

Be strict but fair in your evaluation. Provide specific reasons for your scoring.''')
    
    os.environ['PROMPT_DIR'] = tmp_dir
    
    # Create agents for writer-critic workflow
    writer = LLMAgent(
        AgentConfig(
            name="Writer", 
            model_config={"model": "llama3.2:latest"}
        ), 
        llm_fn=ollama_llm
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
                "model": "llama3.2:latest"
            }
        ),
        llm_fn=ollama_llm
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
    
    # Cleanup
    try:
        os.remove(prompt_file)
        os.rmdir(tmp_dir)
    except:
        pass


if __name__ == "__main__":
    main()

