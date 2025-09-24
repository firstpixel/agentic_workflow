# Agentic Workflow Framework - Comprehensive Project Analysis

## Overview

The Agentic Workflow Framework is a sophisticated Python-based system implementing 20 foundational agentic AI design patterns for building multi-agent systems with orchestrated workflows. The framework provides a production-ready implementation that enables developers to create complex multi-agent systems with features like orchestrated workflows, memory management, error handling, safety guardrails, performance monitoring, and human-in-the-loop capabilities.

## Folder Structure & Design

```
agentic_workflow/
├── src/                          # Main source code
│   ├── core/                     # Core framework components
│   │   ├── types.py             # Core data types (Message, Result, ControlFlag)
│   │   ├── agent.py             # Base agent classes (BaseAgent, LLMAgent)
│   │   ├── workflow_manager.py  # Workflow orchestration engine
│   │   ├── utils.py             # Display/text utilities
│   │   └── event_bus.py         # Event-driven communication
│   ├── agents/                   # Agent implementations (20+ agents)
│   │   ├── planner_agent.py     # Multi-stage planning agent
│   │   ├── switch_agent.py      # Routing/switching agent
│   │   ├── critic_agent.py      # Content evaluation agent
│   │   ├── tool_runner.py       # Tool execution agent
│   │   ├── guardrails_agent.py  # Safety/moderation agent
│   │   └── ...                  # Other specialized agents
│   ├── app/                      # Application layer & flow builders
│   │   ├── main.py              # Demo applications
│   │   ├── flows.py             # Flow builder utilities
│   │   ├── flows_planner.py     # Planner-specific flows
│   │   └── flows_*.py           # Domain-specific flows
│   ├── config/                   # Configuration management
│   │   └── settings.py          # Environment-based settings
│   ├── memory/                   # Memory management systems
│   │   ├── memory_manager.py    # Unified memory interface
│   │   ├── mongo_stm.py         # Short-term memory (MongoDB)
│   │   └── qdrant_store.py      # Long-term memory (Vector DB)
│   ├── eval/                     # Evaluation & metrics
│   │   ├── metrics.py           # Performance metrics
│   │   └── evaluation.py        # Evaluation framework
│   ├── tools/                    # External tool integrations
│   │   └── duckduckgo_scraper.py # Web scraping tool
│   └── guardrails/               # Safety & content filtering
│       └── guardrails.py        # Content moderation
├── prompts/                      # LLM prompts and templates
│   ├── planner/                 # Multi-stage planner prompts
│   │   ├── decomposer.md        # Task decomposition
│   │   ├── summarizer.md        # Planning summary
│   │   ├── detailer.md          # Task detailing
│   │   ├── merger.md            # Task merging/ordering
│   │   ├── evaluator.md         # Plan evaluation
│   │   └── refiner.md           # Plan refinement
│   └── *.md                     # Agent-specific prompts
├── tests/                        # Test suite
├── debug_workflow.py            # Debugging utilities
├── demo_patterns.py             # Pattern demonstrations
└── requirements.txt             # Dependencies
```

## Core Architecture Components

### 1. Core Types System (`src/core/types.py`)

The foundation of the framework built on three core types:

#### Message
```python
@dataclass
class Message:
    data: Any                      # Payload data
    meta: Dict[str, Any]          # Metadata (routing, history, etc.)
```

#### Result  
```python
@dataclass
class Result:
    success: bool                  # Success/failure flag
    output: Any                   # Agent output data
    display_output: Optional[str] # Human-readable output
    control: ControlFlag          # Workflow control flags
    metrics: Dict[str, Any]       # Performance metrics
    overrides: Dict[str, Any]     # Configuration overrides
```

#### ControlFlag
```python
ControlFlag = Dict[str, Any]
# Supported flags:
# - goto: Optional[str]   -> Jump to specific node
# - repeat: bool          -> Repeat previous producer (reflection loop)
# - halt: bool            -> Terminate workflow
```

**Public Contracts:**
- `Result.ok()` - Create successful result
- `Result.fail()` - Create failed result
- `Message.get(key, default)` - Safe data access

### 2. Agent System (`src/core/agent.py`)

#### BaseAgent
Abstract base class for all agents:

```python
class BaseAgent:
    def __init__(self, config: AgentConfig)
    def run(self, message: Message) -> Result    # Override this
    def execute(self, message: Message) -> Result # Handles retries/errors
```

#### LLMAgent
Ollama-integrated LLM agent:

```python
class LLMAgent(BaseAgent):
    # Expects: message.data = {"user_prompt": str, "history": Optional[List]}
    # Returns: {"text": str} in Result.output
```

#### AgentConfig
```python
@dataclass
class AgentConfig:
    name: str                           # Agent identifier
    retries: int = 0                   # Retry attempts
    model_config: Dict[str, Any]       # Model configuration
    prompt_file: Optional[str]         # Markdown prompt file
    history_max_messages: int = 8      # Chat history limit
```

**Public Contracts:**
- All agents inherit from `BaseAgent`
- Override `run(message: Message) -> Result`
- Use `AgentConfig` for configuration
- LLM agents use `prompt_file` for system prompts

### 3. Workflow Management (`src/core/workflow_manager.py`)

The orchestration engine that manages agent execution:

#### WorkflowManager
```python
class WorkflowManager:
    def __init__(self, graph: Dict[str, List[str]], agents: Dict[str, BaseAgent])
    def run_workflow(self, entry: str, input_data: Any) -> List[Result]
```

**Features:**
- Graph-based workflow execution
- Retry/fallback mechanisms with node policies
- Join node support for parallel flows
- Override system for dynamic configuration
- Metrics collection integration

**Node Policies:**
```python
node_policies = {
    "AgentName": {
        "max_retries": 2,              # Retry attempts
        "on_error": "FallbackAgent",   # Fallback agent
        "retry_on_failure": True       # Retry on Result.success=False
    }
}
```

**Public Contracts:**
- `run_workflow(entry, data)` - Execute workflow from entry point
- `get_retry_history()` - Access retry/failure history
- Graph format: `{"NodeA": ["NodeB", "NodeC"], ...}`

## Agent Implementations

### PlannerAgent (`src/agents/planner_agent.py`)

**Deep Analysis - Most Complex Agent:**

Multi-stage planning agent that breaks complex requests into executable task lists using 6 distinct LLM stages:

#### Architecture
```python
class PlannerAgent(BaseAgent):
    STAGE_FILES = {
        "decomposer": "planner/decomposer.md",    # Task breakdown
        "summarizer": "planner/summarizer.md",   # Overview creation
        "detailer": "planner/detailer.md",       # Task expansion
        "merger": "planner/merger.md",           # Task ordering
        "evaluator": "planner/evaluator.md",     # Quality evaluation
        "refiner": "planner/refiner.md"          # Plan refinement
    }
```

#### Execution Flow
1. **Decomposition** - Break request into atomic tasks
2. **Summarization** - Create project overview and constraints
3. **Detailing** - Expand each task with full specifications
4. **Merging** - Order tasks and identify milestones
5. **Evaluation** - Quality check with PASS/REVISE decision
6. **Refinement** - (If needed) Fix issues and iterate

#### Input/Output Contracts
```python
# Input: Message.data can be:
# - str: Direct request
# - {"text": str}: Request wrapper
# - {"refine_request": str}: Refinement mode

# Output: Result.output contains:
{
    "summary_md": str,          # Project overview
    "final_plan_md": str,       # Complete plan
    "tasks_md": List[str],      # Individual task descriptions
    "plan_meta": {              # Metadata
        "executor_agent": str,
        "task_count": int,
        "ordered_task_ids": List[str]
    }
}
```

#### Model Configuration
```python
model_config = {
    "executor_agent": "ExecutorAgent",     # Target executor
    "model": "llama3.2:latest",           # Base model
    "stage_overrides": {                   # Per-stage config
        "decomposer": {"temperature": 0.1},
        "evaluator": {"temperature": 0.0}
    }
}
```

#### Public API
- `run(message)` - Main planning execution
- `_call_stage(stage, vars)` - Execute individual stage
- `_run_refinement(request, executor)` - Handle refinement requests
- Supports both fresh planning and iterative refinement

### SwitchAgent (`src/agents/switch_agent.py`)

Hybrid routing agent supporting keyword-based and LLM-based routing:

#### Configuration
```python
model_config = {
    "mode": "hybrid",                    # "hybrid", "llm", "keywords"
    "confidence_threshold": 0.55,
    "routes": {
        "Billing": {
            "keywords": ["bill", "invoice"],
            "description": "Billing and payments"
        },
        "Support": {
            "keywords": ["error", "bug"],
            "description": "Technical support"
        }
    },
    "default": "Support"
}
```

#### Public Contracts
- Input: `{"text": str}` - Text to route
- Output: `{"route": str, "confidence": float, "mode": str}`
- Control: `{"goto": route}` - Automatic routing

### Other Key Agents

#### CriticAgent - Content Evaluation
- Evaluates content against rubrics
- Returns PASS/REVISE decisions
- Supports iterative improvement loops

#### GuardrailsAgent - Safety & Moderation
- PII detection and redaction
- Content moderation (regex + LLM)
- Input/output filtering

#### ToolRunnerAgent - External Tool Integration
- Supports DuckDuckGo search/scraping
- Extensible tool registry
- Markdown-based tool invocation

## Flow Builder System (`src/app/flows.py`)

### FlowBuilder Class
Fluent API for constructing workflows:

```python
@dataclass
class FlowBuilder:
    def add(self, name: str, agent_instance: Any) -> "FlowBuilder"
    def chain(self, *names: str) -> "FlowBuilder"           # Sequential connection
    def connect(self, src: str, dst: str) -> "FlowBuilder"  # Direct connection
    def build() -> Tuple[Dict[str, Any], Dict[str, List[str]]]
    def manager(self) -> WorkflowManager                    # Create manager
```

### Example Usage
```python
# Simple chain: A -> B -> C
fb = FlowBuilder()
fb.add("A", AgentA()).add("B", AgentB()).add("C", AgentC())
fb.chain("A", "B", "C")
wm = fb.manager()

# Complex flow with branching
fb.connect("Router", "BillingAgent")
fb.connect("Router", "SupportAgent")
```

### Pre-built Flow Helpers
- `make_prompt_handoff_flow()` - Prompt switching patterns
- `make_guardrails_writer_flow()` - Safety + content generation
- `make_hil_writer_flow()` - Human-in-the-loop approval

## Memory System (`src/memory/`)

### Three-Layer Memory Architecture

#### 1. Short-Term Memory (STM) - MongoDB
```python
class MongoSTM:
    def add(self, session_id: str, role: str, content: str)
    def get_recent(self, session_id: str, limit: int = 10)
    def clear_session(self, session_id: str)
```

#### 2. Long-Term Memory (LTM) - Qdrant Vector DB
```python
class QdrantVectorStore:
    def index_document(self, text: str, meta: Dict[str, Any])
    def search(self, query: str, top_k: int = 5)
    def delete_by_meta(self, filters: Dict[str, Any])
```

#### 3. Unified Memory Manager
```python
class MemoryManager:
    def __init__(self, stm: MongoSTM, ltm: QdrantVectorStore)
    def stm_add(self, session_id: str, role: str, content: str)
    def ltm_search(self, query: str, top_k: int = 5)
    def index_document(self, text: str, meta: Dict[str, Any])
```

## File Dependencies Graph

### Core Dependencies
```
main.py -> workflow_manager.py, flows.py, agents/*
workflow_manager.py -> agent.py, types.py, metrics.py
agent.py -> types.py, utils.py, settings.py
flows.py -> workflow_manager.py, agent.py
```

### Agent Dependencies
```
planner_agent.py -> agent.py (LLMAgent), types.py, utils.py
switch_agent.py -> agent.py (LLMAgent), types.py
critic_agent.py -> agent.py (LLMAgent), types.py
tool_runner.py -> agent.py, tools/duckduckgo_scraper.py
guardrails_agent.py -> agent.py, guardrails/guardrails.py
```

### Memory Dependencies
```
memory_manager.py -> mongo_stm.py, qdrant_store.py
mongo_stm.py -> pymongo
qdrant_store.py -> qdrant-client, sentence-transformers
```

### Application Dependencies
```
flows_planner.py -> planner_agent.py, workflow_manager.py
flows_retries.py -> workflow_manager.py, agent.py
flows_tools.py -> tool_runner.py, workflow_manager.py
```

## Creating New Flows - Simplicity Guidelines

### 1. Basic Flow Pattern
```python
from src.app.flows import FlowBuilder
from src.core.agent import AgentConfig, LLMAgent

# Step 1: Create agents
writer = LLMAgent(AgentConfig(
    name="Writer",
    prompt_file="writer.md",
    model_config={"model": "llama3.2:latest"}
))

# Step 2: Build flow
flow = FlowBuilder()
flow.add("Writer", writer)
wm = flow.manager()

# Step 3: Execute
results = wm.run_workflow("Writer", {"user_prompt": "Write a summary"})
```

### 2. Multi-Agent Chain
```python
# Create multiple agents
planner = PlannerAgent(AgentConfig(name="Planner"))
executor = LLMAgent(AgentConfig(name="Executor", prompt_file="executor.md"))

# Chain them
flow = FlowBuilder()
flow.add("Planner", planner).add("Executor", executor)
flow.chain("Planner", "Executor")

# Execute
wm = flow.manager()
results = wm.run_workflow("Planner", {"text": "Create a web API"})
```

### 3. Parallel Processing
```python
# Parallel branches
writer1 = LLMAgent(AgentConfig(name="TechWriter", prompt_file="tech.md"))
writer2 = LLMAgent(AgentConfig(name="BizWriter", prompt_file="biz.md"))
joiner = JoinAgent(AgentConfig(name="Join"))

flow = FlowBuilder()
flow.add("TechWriter", writer1).add("BizWriter", writer2).add("Join", joiner)
flow.connect("Start", "TechWriter").connect("Start", "BizWriter")
flow.connect("TechWriter", "Join").connect("BizWriter", "Join")
```

### 4. Routing Patterns
```python
# Dynamic routing
router = SwitchAgent(AgentConfig(
    name="Router",
    model_config={
        "routes": {
            "Technical": {"keywords": ["code", "API"]},
            "Business": {"keywords": ["plan", "strategy"]}
        }
    }
))

tech_agent = LLMAgent(AgentConfig(name="Technical", prompt_file="tech.md"))
biz_agent = LLMAgent(AgentConfig(name="Business", prompt_file="biz.md"))

flow = FlowBuilder()
flow.add("Router", router).add("Technical", tech_agent).add("Business", biz_agent)
flow.connect("Router", "Technical").connect("Router", "Business")
```

## Configuration System

### Settings Management (`src/config/settings.py`)
Environment-based configuration with sensible defaults:

```python
class Settings:
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    prompt_dir: str = "prompts"
    qdrant_url: str = "http://localhost:6333"
    mongo_uri: str = "mongodb://localhost:27017"
```

### Model Configuration Patterns
```python
# Simple model config
{"model": "llama3.2:latest", "temperature": 0.1}

# Advanced model config with overrides
{
    "model": "llama3.2:latest",
    "options": {"temperature": 0.1, "top_p": 0.9},
    "stage_overrides": {  # For multi-stage agents
        "planning": {"temperature": 0.0},
        "creative": {"temperature": 0.8}
    }
}
```

## Evaluation & Metrics

### MetricsCollector (`src/eval/metrics.py`)
Comprehensive performance tracking:

```python
class MetricsCollector:
    def on_start_node(self, node: str)
    def on_end_node(self, node: str, data: Dict)
    def on_error_node(self, node: str, data: Dict)
    def summary() -> Dict[str, Any]
    def to_csv() -> str
```

### EvaluationRunner (`src/eval/evaluation.py`)
Automated evaluation with regex and LLM judges:

```python
@dataclass
class EvalCase:
    case_id: str
    entry_node: str
    input_data: Any
    required_regex: Optional[str] = None

class EvaluationRunner:
    def run(self, cases: List[EvalCase], judge: str = "regex") -> List[EvalResult]
```

## Error Handling & Resilience

### Retry Mechanisms
- Agent-level retries in `BaseAgent.execute()`
- Workflow-level retries with node policies
- Fallback agents for error recovery

### Node Policies
```python
node_policies = {
    "CriticalAgent": {
        "max_retries": 3,
        "on_error": "FallbackAgent",
        "retry_on_failure": True
    }
}
```

### Error Types
- `WorkflowError` - Workflow execution failures
- `AgentExecutionError` - Agent-specific failures
- Automatic retry with exponential backoff

## Safety & Guardrails

### Content Moderation
- PII detection and redaction
- Keyword-based filtering
- LLM-based content evaluation
- Input/output sanitization

### Human-in-the-Loop
- `ApprovalGateAgent` for human checkpoints
- Event bus integration for async approvals
- Workflow pausing and resumption

## Refactoring Recommendations

### 1. Architecture Improvements

#### Dependency Injection
**Current Issue:** Hard-coded dependencies in agents
**Solution:** Implement dependency injection container
```python
# Proposed
class AgentContainer:
    def register(self, interface: Type, implementation: Type)
    def resolve(self, interface: Type) -> Any
```

#### Interface Segregation
**Current Issue:** Large agent interfaces
**Solution:** Split into focused interfaces
```python
# Proposed
class TextProcessor(Protocol):
    def process_text(self, text: str) -> str

class StateManager(Protocol):
    def save_state(self, state: Any) -> None
    def load_state(self) -> Any
```

### 2. Performance Optimizations

#### Async Processing
**Current Issue:** Synchronous execution only
**Solution:** Add async support for I/O operations
```python
# Proposed
class AsyncBaseAgent:
    async def run_async(self, message: Message) -> Result
```

#### Caching Layer
**Current Issue:** No caching for LLM responses
**Solution:** Implement response caching
```python
# Proposed
class CachedLLMAgent(LLMAgent):
    def __init__(self, config: AgentConfig, cache: Cache)
```

#### Connection Pooling
**Current Issue:** New connections per request
**Solution:** Connection pooling for external services

### 3. Code Organization

#### Agent Registry
**Current Issue:** Manual agent imports
**Solution:** Automatic agent discovery
```python
# Proposed
class AgentRegistry:
    def register_agent(self, name: str, agent_class: Type[BaseAgent])
    def create_agent(self, name: str, config: AgentConfig) -> BaseAgent
```

#### Plugin System
**Current Issue:** Monolithic agent implementations
**Solution:** Plugin architecture for extensibility
```python
# Proposed
class AgentPlugin:
    def install(self, agent: BaseAgent) -> None
    def uninstall(self, agent: BaseAgent) -> None
```

### 4. Testing & Quality

#### Test Coverage
- **Current:** Basic integration tests
- **Recommended:** Unit tests for all agents, mocking for external services

#### Documentation
- **Current:** README and inline comments
- **Recommended:** API documentation, architecture decision records

#### Type Safety
- **Current:** Partial type hints
- **Recommended:** Complete type annotations, mypy integration

### 5. Monitoring & Observability

#### Structured Logging
**Current Issue:** Print statements for debugging
**Solution:** Structured logging with levels
```python
# Proposed
import structlog
logger = structlog.get_logger()
logger.info("workflow_started", entry_node=entry, input_size=len(data))
```

#### Distributed Tracing
**Current Issue:** No cross-agent tracing
**Solution:** OpenTelemetry integration for distributed tracing

#### Health Checks
**Current Issue:** No service health monitoring
**Solution:** Health check endpoints for all services

## Public Contracts Summary

### Core Framework
- `BaseAgent.run(message: Message) -> Result` - Agent execution interface
- `WorkflowManager.run_workflow(entry: str, data: Any) -> List[Result]` - Workflow execution
- `FlowBuilder` - Fluent API for workflow construction
- `Result.ok()/Result.fail()` - Result creation utilities

### Agent Interfaces
- `LLMAgent` - Expects `{"user_prompt": str, "history": Optional[List]}`
- `PlannerAgent` - Multi-stage planning with refinement support
- `SwitchAgent` - Hybrid routing with confidence thresholds
- `CriticAgent` - Content evaluation with iterative feedback
- `ToolRunnerAgent` - External tool integration with safety checks

### Memory System
- `MemoryManager` - Unified STM/LTM interface
- `MongoSTM` - Session-based short-term memory
- `QdrantVectorStore` - Semantic search capabilities

### Configuration
- `AgentConfig` - Standard agent configuration
- `Settings` - Environment-based global configuration
- Node policies for retry/fallback behavior

## Conclusion

The Agentic Workflow Framework provides a comprehensive foundation for building sophisticated multi-agent systems. Its modular architecture, extensive agent library, and robust orchestration capabilities make it suitable for complex real-world applications. The framework's emphasis on safety, monitoring, and human-in-the-loop capabilities demonstrates production-readiness.

Key strengths include the flexible workflow management system, comprehensive agent implementations (especially the PlannerAgent), and the clean separation of concerns between core framework, agents, and application layers. The flow builder system makes it easy to create new workflows while maintaining the flexibility to handle complex routing and parallel processing scenarios.

For future development, focus should be placed on implementing the recommended refactoring improvements, particularly around async processing, caching, and enhanced monitoring capabilities.