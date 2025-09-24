# Agentic AI Workflow Framework

A comprehensive Python framework implementing 20 foundational agentic AI design patterns for building sophisticated multi-agent systems with orchestrated workflows.

## 📋 Table of Contents

1. [Overview](#overview)
2. [20 Agentic AI Design Patterns](#20-agentic-ai-design-patterns)
3. [Project Architecture](#project-architecture)
4. [Installation & Setup](#installation--setup)
5. [Usage Examples](#usage-examples)
6. [Pattern Implementations](#pattern-implementations)
7. [Core Components](#core-components)
8. [Testing](#testing)
9. [Contributing](#contributing)

## 🎯 Overview

This framework provides a production-ready implementation of 20 essential agentic AI design patterns, enabling developers to build complex multi-agent systems with features like:

- **Orchestrated Workflows**: Chain agents with complex control flow
- **Memory Management**: Short-term, episodic, and long-term storage
- **Error Handling**: Retry mechanisms and fallback strategies  
- **Safety & Guardrails**: Input/output filtering and content moderation
- **Performance Monitoring**: Metrics collection and evaluation
- **Human-in-the-Loop**: Approval gates and intervention points

## 🔄 20 Agentic AI Design Patterns

### 1. **Prompt Chaining** 
*Sequential task decomposition with validation*

```
[User Request] → [Step A] → [Step B] → [Step C] → [Final Result]
```

**Implementation**: Sequential workflow execution via `WorkflowManager`
- **Files**: `src/core/workflow_manager.py`, `tests/test_workflow_basic.py`
- **Example**: Multi-step document generation pipeline

### 2. **Routing**
*Intelligent request distribution to specialized agents*

```
[User Request] → [Router Agent] → [Billing Agent]
                              → [Support Agent] 
                              → [Sales Agent]
```

**Implementation**: `SwitchAgent` with rule-based and LLM-based routing
- **Files**: `src/agents/switch_agent.py`, `tests/test_switch_agent.py`
- **Example**: Customer service request classification

### 3. **Parallelization**
*Concurrent execution of independent subtasks*

```
[Large Task] → [Subtask A] → [Agent A] → [Result A]
             → [Subtask B] → [Agent B] → [Result B] → [Combine Results]
```

**Implementation**: `FanOutAgent` and `JoinAgent` for parallel execution
- **Files**: `src/agents/fanout_agent.py`, `src/agents/join_agent.py`
- **Example**: Parallel document analysis and summarization

### 4. **Reflection**
*Iterative improvement through criticism and revision*

```
[Agent] → [Draft] → [Critic Agent] → [Feedback] → [Revision] → [Final Version]
```

**Implementation**: `CriticAgent` with configurable feedback loops
- **Files**: `src/agents/critic_agent.py`, `tests/test_critic_agent.py`
- **Example**: Iterative content refinement

### 5. **Tool Use**
*External tool integration for specialized capabilities*

```
[Agent] → [Tool Selection] → [Query Tool] → [Tool Output] → [Incorporate Results]
```

**Implementation**: `ToolRunnerAgent` with configurable tool specifications
- **Files**: `src/agents/tool_runner.py`, `src/tools/duckduckgo_scraper.py`
- **Example**: Web search integration for real-time information

### 6. **Planning**
*Multi-step plan generation and execution*

```
[Goal] → [Planning Agent] → [Step 1] → [Step 2] → [Step 3]
                         → [Tool: Web Search] → [Agent: Analyzer] → [Report Generator]
```

**Implementation**: `PlannerAgent` with decomposition, refinement, and evaluation
- **Files**: `src/agents/planner_agent.py`, `src/app/flows_planner.py`
- **Example**: Research project planning and execution

### 7. **Multi-Agent Collaboration**
*Coordinated teamwork with shared memory*

```
[Manager Agent] → [Agent A] → [Common Memory]
               → [Agent B] ↗
               → [Agent C] ↗
```

**Implementation**: `WorkflowManager` with shared `MemoryManager`
- **Files**: `src/core/workflow_manager.py`, `src/memory/memory_manager.py`
- **Example**: Collaborative document creation

### 8. **Memory Management**
*Multi-tier information storage and retrieval*

```
[Info] → [Memory Manager] → [Short-Term (Conversation)]
                         → [Episodic (Events)]
                         → [Long-Term (Knowledge)]
```

**Implementation**: `MemoryManager` with MongoDB and Qdrant backends
- **Files**: `src/memory/memory_manager.py`, `src/memory/mongo_stm.py`, `src/memory/qdrant_store.py`
- **Example**: Persistent conversation and knowledge storage

### 9. **Learning and Adaptation**
*Continuous improvement through feedback*

```
[Output] → [Feedback] → [Update Prompts/Policies] → [Improved Agent]
```

**Implementation**: Feedback collection and prompt updating mechanisms
- **Files**: `src/eval/evaluation.py`, `src/core/agent.py` (overrides system)
- **Example**: Model performance optimization

### 10. **Goal Setting and Monitoring**
*Progress tracking and plan adjustment*

```
[Goal] → [Define Metrics] → [Monitor Progress] → [Adjust Plan]
```

**Implementation**: `MetricsCollector` and workflow monitoring
- **Files**: `src/eval/metrics.py`, `src/core/workflow_manager.py`
- **Example**: Task completion tracking

### 11. **Exception Handling and Recovery**
*Robust error management and fallback strategies*

```
[Task] → [Error] → [Retry] → [Fallback Method] → [Human Intervention]
```

**Implementation**: Retry policies and fallback nodes in workflow
- **Files**: `src/core/workflow_manager.py`, `src/app/flows_retries.py`
- **Example**: Network failure recovery with alternative data sources

### 12. **Human in the Loop**
*Strategic human intervention points*

```
[Workflow] → [Critical Decision] → [Human Review] → [Continue]
```

**Implementation**: `ApprovalGateAgent` with EventBus integration
- **Files**: `src/agents/approval_gate.py`, `src/core/event_bus.py`
- **Example**: Content approval before publication

### 13. **Knowledge Retrieval (RAG)**
*Grounded responses using external knowledge*

```
[Query] → [Embeddings] → [Vector DB] → [Relevant Docs] → [Grounded Response]
```

**Implementation**: `RAGRetrieverAgent` with vector similarity search
- **Files**: `src/agents/rag_retriever.py`, `tests/test_pattern_rag.py`
- **Example**: Document-grounded question answering

### 14. **Inter-Agent Communication**
*Structured messaging between agents*

```
[Agent A] → [Message (ID, Protocol, Data)] → [Agent B]
```

**Implementation**: EventBus system for agent communication
- **Files**: `src/core/event_bus.py`, message passing in workflows
- **Example**: Notification and coordination between agents

### 15. **Resource-Aware Optimization**
*Cost-effective model selection*

```
[Task] → [Analyze Complexity] → [Cheap Model] / [Powerful Model]
```

**Implementation**: `ModelSelectorAgent` with complexity analysis
- **Files**: `src/agents/model_selector.py`, `tests/test_pattern_model_selector.py`
- **Example**: Dynamic model selection based on task complexity

### 16. **Reasoning Techniques**
*Specialized problem-solving approaches*

```
[Problem] → [Select Method] → [Chain-of-Thought] / [Tree-of-Thought] / [Debate]
```

**Implementation**: Configurable reasoning prompts and techniques
- **Files**: Specialized prompts in `prompts/` directory
- **Example**: Mathematical problem solving with step-by-step reasoning

### 17. **Evaluation and Monitoring**
*Continuous performance assessment*

```
[Model] → [Pre-deployment Tests] → [Deploy] → [Continuous Monitoring]
```

**Implementation**: `EvaluationRunner` and `MetricsCollector`
- **Files**: `src/eval/evaluation.py`, `src/eval/metrics.py`
- **Example**: A/B testing and performance tracking

### 18. **Guardrails and Safety Patterns**
*Content safety and compliance checking*

```
[Input] → [Guardrail System] → [Block/Allow] → [Agent] → [Output Validation]
```

**Implementation**: `GuardrailsAgent` with PII detection and content moderation
- **Files**: `src/agents/guardrails_agent.py`, `src/guardrails/guardrails.py`
- **Example**: Content filtering and PII redaction

### 19. **Prioritization**
*Task ordering and resource allocation*

```
[Tasks] → [Prioritization Engine] → [Ordered Queue] → [Execute by Priority]
```

**Implementation**: Task scoring and queue management
- **Files**: Workflow priority handling in `WorkflowManager`
- **Example**: Customer support ticket prioritization

### 20. **Exploration and Discovery**
*Knowledge space exploration and hypothesis generation*

```
[Topic] → [Exploration Agent] → [Pattern Identification] → [Hypothesis Generation]
```

**Implementation**: Search agents and pattern analysis
- **Files**: `src/tools/duckduckgo_scraper.py`, exploration workflows
- **Example**: Market research and trend analysis

## 🏗️ Project Architecture

```
src/
├── core/                    # Core framework components
│   ├── agent.py            # Base agent classes and LLM integration
│   ├── types.py            # Message, Result, and control structures
│   ├── workflow_manager.py # Orchestration and flow control
│   ├── event_bus.py        # Inter-agent communication
│   └── utils.py            # Utility functions
├── agents/                  # Specialized agent implementations
│   ├── approval_gate.py    # Human-in-the-loop approval
│   ├── critic_agent.py     # Reflection and feedback
│   ├── fanout_agent.py     # Parallel task distribution
│   ├── guardrails_agent.py # Safety and content filtering
│   ├── join_agent.py       # Result aggregation
│   ├── model_selector.py   # Dynamic model selection
│   ├── planner_agent.py    # Multi-step planning
│   ├── prompt_switcher.py  # Dynamic prompt selection
│   ├── rag_retriever.py    # Knowledge retrieval
│   ├── switch_agent.py     # Request routing
│   └── tool_runner.py      # External tool integration
├── memory/                  # Memory management system
│   ├── memory_manager.py   # Multi-tier storage coordination
│   ├── mongo_stm.py        # Short-term memory (MongoDB)
│   └── qdrant_store.py     # Vector storage (Qdrant)
├── eval/                    # Evaluation and monitoring
│   ├── evaluation.py       # Test case evaluation
│   └── metrics.py          # Performance metrics collection
├── tools/                   # External tool integrations
│   └── duckduckgo_scraper.py # Web search capability
└── app/                     # Application flows and demos
    ├── main.py             # Demo applications
    ├── flows.py            # Workflow definitions
    ├── flows_planner.py    # Planning demonstrations
    └── flows_retries.py    # Error handling examples
```

### Key Components

#### 1. **WorkflowManager** (`src/core/workflow_manager.py`)
- **Purpose**: Orchestrates multi-agent workflows with complex control flow
- **Features**:
  - Graph-based workflow execution
  - Retry and fallback mechanisms
  - Node state management
  - Parallel execution support
  - Error recovery strategies

#### 2. **BaseAgent & LLMAgent** (`src/core/agent.py`)
- **Purpose**: Foundation for all agent implementations
- **Features**:
  - Configurable retry logic
  - Prompt management system
  - Model configuration
  - Metrics collection
  - History management

#### 3. **MemoryManager** (`src/memory/memory_manager.py`)
- **Purpose**: Multi-tier memory system for agents
- **Features**:
  - Short-term conversational memory (MongoDB)
  - Long-term knowledge storage (Qdrant vectors)
  - Episodic event memory
  - Automatic memory lifecycle management

#### 4. **EventBus** (`src/core/event_bus.py`)
- **Purpose**: Enables inter-agent communication and coordination
- **Features**:
  - Publish/subscribe messaging
  - Event filtering and routing
  - Asynchronous communication
  - Human-in-the-loop integration

## 🚀 Installation & Setup

### Prerequisites
- Python 3.8+
- Ollama (for local LLM inference)
- MongoDB (for short-term memory)
- Qdrant (for vector storage)

### Installation

1. **Clone the repository**:
```bash
git clone <repository-url>
cd agentic_workflow
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Set up external services**:

**Ollama** (Local LLM):
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:latest
```

**MongoDB** (Docker):
```bash
docker run -d --name mongodb -p 27017:27017 mongo:latest
```

**Qdrant** (Docker):
```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:latest
```

4. **Configure environment**:
Create `.env` file:
```bash
OLLAMA_MODEL=llama3.2:latest
MONGODB_URL=mongodb://localhost:27017
QDRANT_URL=http://localhost:6333
PROMPT_DIR=./prompts
```

## 📖 Usage Examples

### Basic Agent Usage

```python
from src.core.agent import AgentConfig, LLMAgent
from src.core.types import Message

# Create a simple writing agent
writer = LLMAgent(AgentConfig(
    name="Writer",
    prompt_file="tech_writer.md",
    model_config={"model": "llama3.2:latest", "temperature": 0.7}
))

# Execute the agent
message = Message(data={"user_prompt": "Write a brief intro to AI"})
result = writer.execute(message)
print(result.output)
```

### Workflow Orchestration

```python
from src.core.workflow_manager import WorkflowManager
from src.agents.critic_agent import CriticAgent

# Define workflow graph
graph = {
    "Writer": ["Critic"],
    "Critic": ["Writer"],  # Enables reflection loop
    "Writer": []  # Final output
}

# Create agents
writer = LLMAgent(AgentConfig(name="Writer", prompt_file="tech_writer.md"))
critic = CriticAgent(AgentConfig(name="Critic", prompt_file="critic_agent.md"))

# Create workflow
workflow = WorkflowManager(
    graph=graph,
    agents={"Writer": writer, "Critic": critic}
)

# Execute workflow
result = workflow.run(Message(data={"user_prompt": "Write about quantum computing"}))
```

### RAG (Retrieval Augmented Generation)

```python
from src.agents.rag_retriever import RAGRetrieverAgent
from src.memory.memory_manager import MemoryManager

# Setup memory system
memory = MemoryManager()

# Create RAG agent
rag_agent = RAGRetrieverAgent(AgentConfig(
    name="RAG",
    prompt_file="answer_with_context.md"
))

# Store knowledge
memory.store_long_term("AI History", "content", {"text": "AI was founded in 1956..."})

# Query with retrieval
message = Message(data={
    "user_prompt": "When was AI founded?",
    "memory_manager": memory
})
result = rag_agent.execute(message)
```

### Human-in-the-Loop Approval

```python
from src.agents.approval_gate import ApprovalGateAgent
from src.core.event_bus import get_event_bus

# Setup approval system
bus = get_event_bus()
approval_agent = ApprovalGateAgent(AgentConfig(
    name="ApprovalGate",
    prompt_file="approval_request.md"
))

# Request approval
message = Message(data={
    "content": "This content needs review before publication",
    "approval_type": "content_review"
})

# Agent will pause and wait for human decision via EventBus
result = approval_agent.execute(message)
```

### Parallel Processing

```python
from src.agents.fanout_agent import FanOutAgent
from src.agents.join_agent import JoinAgent

# Create parallel workflow
fanout = FanOutAgent(AgentConfig(name="Fanout"))
join = JoinAgent(AgentConfig(name="Join"))

# Define parallel tasks
graph = {
    "Fanout": ["TaskA", "TaskB", "TaskC"],
    "TaskA": ["Join"],
    "TaskB": ["Join"], 
    "TaskC": ["Join"],
    "Join": []
}

workflow = WorkflowManager(graph=graph, agents={...})
```

## 🧪 Testing

The framework includes comprehensive tests for each pattern:

```bash
# Run all tests
pytest tests/

# Test specific patterns
pytest tests/test_pattern_guardrails.py
pytest tests/test_pattern_rag.py
pytest tests/test_pattern_model_selector.py

# Integration tests
pytest tests/test_workflow_basic.py
pytest tests/test_memory_components.py
```

### Test Categories

- **Pattern Tests**: Validate each of the 20 design patterns
- **Integration Tests**: Test component interactions
- **Performance Tests**: Measure system performance
- **Safety Tests**: Verify guardrails and error handling

## 🔧 Configuration

### Agent Configuration

```python
@dataclass
class AgentConfig:
    name: str
    retries: int = 0                    # Retry attempts on failure
    retry_backoff_sec: float = 0.0      # Delay between retries
    model_config: Dict[str, Any]        # Model parameters
    prompt_file: str                    # Prompt template path
    tools: List[Any]                    # Available tools
    history_max_messages: int = 8       # Conversation history limit
```

### Memory Configuration

```python
# MongoDB for short-term memory
MONGODB_URL = "mongodb://localhost:27017"

# Qdrant for vector storage
QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "knowledge_base"
```

### Model Configuration

```python
model_config = {
    "model": "llama3.2:latest",
    "temperature": 0.7,
    "top_p": 0.9,
    "max_tokens": 1000
}
```

## 🤝 Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature-name`
3. **Add tests** for new functionality
4. **Run the test suite**: `pytest tests/`
5. **Submit a pull request**

### Development Guidelines

- Follow the existing code structure and naming conventions
- Add comprehensive tests for new patterns or agents
- Update documentation for new features
- Use type hints and docstrings
- Ensure all tests pass before submitting

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙋‍♂️ Support

For questions, issues, or contributions:
- **Issues**: Use GitHub Issues for bug reports
- **Discussions**: Use GitHub Discussions for questions
- **Documentation**: Check the `tests/` directory for usage examples

---

**Built with ❤️ for the AI community**

This framework represents a comprehensive implementation of proven agentic AI patterns, providing a solid foundation for building sophisticated multi-agent systems. Each pattern is carefully implemented with production considerations including error handling, monitoring, and scalability.
