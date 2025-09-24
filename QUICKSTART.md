# Quick Start Guide

Get up and running with the Agentic AI Framework in 5 minutes!

## 1. Prerequisites Setup

### Install Ollama (Local LLM)
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.2:3b
ollama pull llama3.2:1b
ollama pull gemma3:latest

# Verify installation
ollama list
```

### Start External Services (Optional)
```bash
# MongoDB (for memory)
docker run -d --name mongodb -p 27017:27017 mongo:latest

# Qdrant (for vector storage)  
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:latest
```

## 2. Install the Framework

```bash
# Clone repository
git clone <your-repo-url>
cd agentic_workflow

# Install dependencies
pip install -r requirements.txt
# OR
pip install -e .
```

## 3. Run Your First Agent

### Simple LLM Agent
```python
from src.core.agent import AgentConfig, LLMAgent
from src.core.types import Message

# Create agent
agent = LLMAgent(AgentConfig(
    name="Writer",
    prompt_file="tech_writer.md"
))

# Execute
message = Message(data={"user_prompt": "Explain quantum computing"})
result = agent.execute(message)
print(result.output)
```

### Multi-Agent Workflow
```python  
from src.core.workflow_manager import WorkflowManager

# Define workflow
graph = {
    "Writer": ["Critic"],
    "Critic": []
}

agents = {
    "Writer": LLMAgent(AgentConfig(name="Writer", prompt_file="tech_writer.md")),
    "Critic": LLMAgent(AgentConfig(name="Critic", prompt_file="critic_agent.md"))
}

# Run workflow
workflow = WorkflowManager(graph=graph, agents=agents)
result = workflow.run(Message(data={"user_prompt": "Write about AI ethics"}))
print(result.output)
```

## 4. Try the Demos

```bash
# Run all pattern demos
python demo_patterns.py

# Run specific pattern
python demo_patterns.py 1  # Prompt chaining
python demo_patterns.py 2  # Routing
```

## 5. Run Tests

```bash
# Test basic functionality
pytest tests/test_workflow_basic.py

# Test specific patterns
pytest tests/test_pattern_guardrails.py
pytest tests/test_pattern_rag.py

# Full test suite
pytest tests/
```

## 🚀 What's Next?

1. **Explore Patterns**: Check out all 20 patterns in the main README
2. **Build Workflows**: Combine multiple patterns for complex tasks  
3. **Add Memory**: Integrate MongoDB/Qdrant for persistent memory
4. **Custom Agents**: Extend `BaseAgent` for domain-specific needs
5. **Add Tools**: Create new tools in `src/tools/`

## 💡 Common Use Cases

- **Content Generation**: Writer → Critic → Approver workflow
- **Research Assistant**: Query → RAG → Summarizer → Critic  
- **Customer Service**: Router → Specialist agents with guardrails
- **Document Processing**: Parallel analyzers → Join → Report generation

Happy building! 🎉