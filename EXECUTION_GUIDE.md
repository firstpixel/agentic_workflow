# 🚀 Execution Guide - Agentic AI Workflow Framework

## Quick Start Commands

### 1. Setup (One-time)

```bash
# Clone and setup
git clone <repository-url>
cd agentic_workflow

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies  
pip install -r requirements.txt

# Install Ollama (for LLM demos)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:latest
```

### 2. Run Demos

#### Pattern Demonstrations (Requires Ollama)
```bash
# Always activate virtual environment first
source .venv/bin/activate

# Run all 20 design patterns
python demo_patterns.py

# Run specific patterns
python demo_patterns.py 1    # Prompt Chaining
python demo_patterns.py 2    # Routing  
python demo_patterns.py 3    # Parallelization
python demo_patterns.py 4    # Reflection
python demo_patterns.py 5    # Tool Use

# Or use helper script (auto-activates .venv)
./run_demo.sh 1
```

#### Code Executor Demo (No LLM required)
```bash
# Demonstrates automated code generation and execution
python demo_code_executor.py

# Creates real projects in ./demo_output/:
# - Python Calculator with tests
# - React ArXiv Browser App  
# - Node.js API Server
# - Static HTML/CSS Website
```

#### Development Tools
```bash  
# Debug workflows and agents
python debug_workflow.py

# Run test suite
pytest tests/

# Run specific pattern tests
pytest tests/test_pattern_guardrails.py
```

### 3. Key Features by Demo

| Demo Script | What It Shows | Requirements |
|-------------|---------------|--------------|
| `demo_patterns.py` | All 20 agentic AI patterns | Ollama + Models |
| `demo_code_executor.py` | Code generation & execution | None (mocked) |
| `debug_workflow.py` | Workflow debugging | Basic Python |
| Test files | Pattern validation | pytest |

### 4. Demo Outputs

- **Pattern Demos**: Console output showing agent interactions
- **Code Executor**: Real files created in `./demo_output/`
- **Tests**: Pass/fail results for each pattern implementation

### 5. Common Use Cases

```bash
# Quick pattern exploration (no setup needed)
python demo_code_executor.py

# Full AI agent experience (requires Ollama)
./run_demo.sh

# Development and testing
pytest tests/test_pattern_*.py

# Custom workflow testing
python debug_workflow.py
```

### 6. Troubleshooting

**Ollama Connection Issues:**
```bash
# Check if Ollama is running
ollama list

# Start Ollama if needed
ollama serve
```

**Virtual Environment Issues:**
```bash
# Make sure you're in the right environment
source .venv/bin/activate
which python  # Should show .venv/bin/python
```

**Missing Dependencies:**
```bash
# Reinstall requirements
pip install -r requirements.txt --upgrade
```

---

## 📚 Next Steps

1. **Explore Patterns**: Start with `demo_code_executor.py` (no setup needed)
2. **Setup LLM**: Install Ollama for full agent experience  
3. **Read Documentation**: Check README.md for detailed explanations
4. **Build Custom Agents**: Extend the framework for your use case
5. **Run Tests**: Validate functionality with `pytest tests/`

**Happy experimenting! 🎉**