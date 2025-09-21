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
from src.core.agent import AgentConfig
from src.core.types import Result
from src.agents.switch_agent import SwitchAgent

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
        "confidence_threshold": 0.55,
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


if __name__ == "__main__":
    main()

