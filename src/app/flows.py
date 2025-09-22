# app/flows.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any

# Importa seus componentes-base (mantendo compatibilidade com sua estrutura)
from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager

# Agentes opcionais (podem não existir dependendo do estágio do repo)
try:
    from src.agents.critic_agent import CriticAgent  # Task 3
except Exception:
    CriticAgent = None

try:
    from src.agents.guardrails_agent import GuardrailsAgent  # Task 6
except Exception:
    GuardrailsAgent = None

try:
    from src.agents.approval_gate import ApprovalGateAgent  # Task 7
except Exception:
    ApprovalGateAgent = None

try:
    from src.agents.model_selector import ModelSelectorAgent as ModelRouterAgent  # Task 9
except Exception:
    ModelRouterAgent = None

try:
    from src.agents.prompt_switcher import PromptSwitcherAgent as PromptAgent  # Task 10
except Exception:
    PromptAgent = None

try:
    from src.agents.query_rewriter import QueryRewriterAgent  # Task 5 (parte rewriter)
except Exception:
    QueryRewriterAgent = None

try:
    from src.agents.fanout_agent import FanOutAgent as FanoutAgent  # Task 4
except Exception:
    FanoutAgent = None

try:
    from src.agents.join_agent import JoinAgent  # Task 4
except Exception:
    JoinAgent = None


# ---------------------------
# FlowBuilder: estrutura leve
# ---------------------------

@dataclass
class FlowBuilder:
    """
    Builder leve para compor agentes e o grafo (dict node -> [next_nodes]).
    """
    agents: Dict[str, Any] = field(default_factory=dict)
    graph: Dict[str, List[str]] = field(default_factory=dict)

    def add(self, name: str, agent_instance: Any) -> "FlowBuilder":
        if name in self.agents:
            raise ValueError(f"Agent '{name}' already exists in flow.")
        self.agents[name] = agent_instance
        self.graph.setdefault(name, [])
        return self

    def chain(self, *names: str) -> "FlowBuilder":
        """
        Conecta sequencialmente (A->B->C...). Cada nome deve já existir via add().
        """
        for i in range(len(names) - 1):
            src, dst = names[i], names[i+1]
            self.graph.setdefault(src, [])
            if dst not in self.graph[src]:
                self.graph[src].append(dst)
            self.graph.setdefault(dst, [])
        return self

    def connect(self, src: str, dst: str) -> "FlowBuilder":
        self.graph.setdefault(src, [])
        if dst not in self.graph[src]:
            self.graph[src].append(dst)
        self.graph.setdefault(dst, [])
        return self

    def build(self) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
        return self.agents, self.graph

    def manager(self, metrics: Optional[Any] = None) -> WorkflowManager:
        return WorkflowManager(self.graph, self.agents, metrics=metrics)


# ---------------------------
# Helpers de fluxos comuns
# ---------------------------

def make_prompt_handoff_flow(
    *,
    model: str,
    prompt_agent_file: str = "prompt_agent.md",
    writer_bullets_file: str = "writer_bullets.md",
    writer_paragraph_file: str = "writer_paragraph.md",
    writer_name: str = "Writer",
    prompt_agent_name: str = "PromptAgent"
) -> FlowBuilder:
    """
    Task 10: Prompt/Plan Handoff
    PromptAgent -> Writer (Writer consome {plan_md} e tem prompt override por arquivo).
    """
    if PromptAgent is None:
        raise RuntimeError("PromptAgent não encontrado. Certifique-se de ter concluído o Task 10.")

    fb = FlowBuilder()

    prompt_agent = PromptAgent(AgentConfig(
        name=prompt_agent_name,
        model_config={
            "prompt_file": prompt_agent_file,
            "model": model,
            "options": {"temperature": 0.0},
            "default_targets": {writer_name: writer_bullets_file}
        }
    ))

    writer = LLMAgent(AgentConfig(
        name=writer_name,
        prompt_file=writer_bullets_file,   # baseline; override virá do PromptAgent
        model_config={"model": model, "options": {"temperature": 0.1}}
    ))

    fb.add(prompt_agent_name, prompt_agent)
    fb.add(writer_name, writer)
    fb.chain(prompt_agent_name, writer_name)
    return fb


def make_guardrails_writer_flow(
    *,
    model: str,
    moderation_file: str = "moderation.md",
    writer_file: str = "tech_writer.md",
    guard_name: str = "Guardrails",
    writer_name: str = "Writer"
) -> FlowBuilder:
    """
    Task 6: Guardrails -> Writer
    """
    if GuardrailsAgent is None:
        raise RuntimeError("GuardrailsAgent não encontrado. Certifique-se de ter concluído o Task 6.")

    fb = FlowBuilder()

    guard = GuardrailsAgent(AgentConfig(
        name=guard_name,
        model_config={
            "pii_redact": True,
            "moderation_mode": "hybrid",
            "moderation_prompt_file": moderation_file,
            "model": model,
            "options": {"temperature": 0.0}
        }
    ))
    writer = LLMAgent(AgentConfig(
        name=writer_name,
        prompt_file=writer_file,
        model_config={"model": model, "options": {"temperature": 0.1}}
    ))

    fb.add(guard_name, guard)
    fb.add(writer_name, writer)
    fb.chain(guard_name, writer_name)
    return fb


def make_hil_writer_flow(
    *,
    model: str,
    approval_file: str = "approval_request.md",
    writer_file: str = "tech_writer.md",
    gate_name: str = "ApprovalGate",
    writer_name: str = "Writer"
) -> FlowBuilder:
    """
    Task 7: Human-in-the-Loop
    Two-phase usage (request then decision); aqui só monta o grafo.
    """
    if ApprovalGateAgent is None:
        raise RuntimeError("ApprovalGateAgent não encontrado. Conclua o Task 7.")

    fb = FlowBuilder()
    gate = ApprovalGateAgent(AgentConfig(
        name=gate_name,
        model_config={
            "summary_prompt_file": approval_file,
            "next_on_approve": writer_name,
            "model": model,
            "options": {"temperature": 0.1}
        }
    ))
    writer = LLMAgent(AgentConfig(
        name=writer_name,
        prompt_file=writer_file,
        model_config={"model": model, "options": {"temperature": 0.1}}
    ))

    fb.add(gate_name, gate)
    fb.add(writer_name, writer)
    fb.chain(gate_name, writer_name)
    return fb


def make_router_writer_critic_join_flow(
    *,
    model: str,
    router_file: str = "model_router.md",
    writer_file: str = "tech_writer.md",
    critic_file: str = "critic_agent.md",
    router_name: str = "ModelRouter",
    writer_name: str = "Writer",
    critic_name: str = "Critic",
    join_name: str = "Join"
) -> FlowBuilder:
    """
    router -> writer -> critic -> join
    - Router ajusta model_config do Writer (Task 9).
    - Critic sinaliza repeat conforme sua rúbrica (Task 3).
    - Join finaliza (aqui default expected_inputs=1; ajuste se houver fan-out real).
    """
    if ModelRouterAgent is None:
        raise RuntimeError("ModelRouterAgent não encontrado. Conclua o Task 9.")
    if CriticAgent is None:
        raise RuntimeError("CriticAgent não encontrado. Conclua o Task 3.")
    if JoinAgent is None:
        raise RuntimeError("JoinAgent não encontrado. Conclua o Task 4.")

    fb = FlowBuilder()

    router = ModelRouterAgent(AgentConfig(
        name=router_name,
        model_config={
            "prompt_file": router_file,
            "model": model,
            "options": {"temperature": 0.0},
            "classes": {
                "SIMPLE":   {"model": model, "options": {"temperature": 0.1}},
                "STANDARD": {"model": model, "options": {"temperature": 0.3}},
                "COMPLEX":  {"model": model, "options": {"temperature": 0.6}}
            },
            "targets": [writer_name]
        }
    ))

    writer = LLMAgent(AgentConfig(
        name=writer_name,
        prompt_file=writer_file,
        model_config={"model": model, "options": {"temperature": 0.3}}
    ))

    critic = CriticAgent(AgentConfig(
        name=critic_name,
        model_config={
            "prompt_file": critic_file,
            "model": model,
            "options": {"temperature": 0.1}
        }
    ))

    join = JoinAgent(AgentConfig(name=join_name))

    fb.add(router_name, router)
    fb.add(writer_name, writer)
    fb.add(critic_name, critic)
    fb.add(join_name, join)

    fb.chain(router_name, writer_name).chain(writer_name, critic_name).chain(critic_name, join_name)
    return fb


def make_parallel_join_flow(
    *,
    model: str,
    fanout_name: str = "Fanout",
    a_name: str = "A",
    b_name: str = "B",
    join_name: str = "Join",
    a_prompt_file: str = "writer_bullets.md",
    b_prompt_file: str = "writer_paragraph.md"
) -> FlowBuilder:
    """
    Task 4: Fan-out -> (A,B) -> Join
    """
    if FanoutAgent is None or JoinAgent is None:
        raise RuntimeError("FanoutAgent/JoinAgent não encontrados. Conclua o Task 4.")

    fb = FlowBuilder()

    fan = FanoutAgent(AgentConfig(name=fanout_name))
    a = LLMAgent(AgentConfig(name=a_name, prompt_file=a_prompt_file, model_config={"model": model, "options": {"temperature": 0.1}}))
    b = LLMAgent(AgentConfig(name=b_name, prompt_file=b_prompt_file, model_config={"model": model, "options": {"temperature": 0.3}}))
    join = JoinAgent(AgentConfig(name=join_name))

    fb.add(fanout_name, fan).add(a_name, a).add(b_name, b).add(join_name, join)
    fb.connect(fanout_name, a_name).connect(fanout_name, b_name)
    fb.connect(a_name, join_name).connect(b_name, join_name)
    return fb


def make_rewriter_writer_flow(
    *,
    model: str,
    rewriter_file: str = "query_rewriter.md",
    writer_file: str = "answer_with_context.md",
    rewriter_name: str = "QueryRewriter",
    writer_name: str = "Answerer"
) -> FlowBuilder:
    """
    Task 5 (parte): Rewriter -> Writer (simples)
    """
    if QueryRewriterAgent is None:
        raise RuntimeError("QueryRewriterAgent não encontrado. Conclua o Task 5.")

    fb = FlowBuilder()

    rew = QueryRewriterAgent(AgentConfig(
        name=rewriter_name,
        model_config={"prompt_file": rewriter_file, "model": model, "options": {"temperature": 0.0}}
    ))
    ans = LLMAgent(AgentConfig(
        name=writer_name,
        prompt_file=writer_file,
        model_config={"model": model, "options": {"temperature": 0.1}}
    ))

    fb.add(rewriter_name, rew).add(writer_name, ans).chain(rewriter_name, writer_name)
    return fb
