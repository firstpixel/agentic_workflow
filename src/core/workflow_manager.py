from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Deque, Tuple
from collections import deque, defaultdict

from .types import Message, Result, WorkflowError
from .agent import BaseAgent


@dataclass
class NodeState:
    expected_inputs: int = 1
    received: List[Message] = field(default_factory=list)
    last_producer: Optional[str] = None  # para repeat loops


class WorkflowManager:
    """
    - Grafo simples: node -> [next_nodes]
    - Respeita control flags: goto, repeat, halt
    - Mantém 'root' (input original) e 'iteration' para reflexão
    """
    def __init__(self, graph: Dict[str, List[str]], agents: Dict[str, BaseAgent]):
        self.graph = graph
        self.agents = agents
        self.state: Dict[str, NodeState] = defaultdict(NodeState)
        self.run_overrides: Dict[str, Dict[str, Any]] = defaultdict(dict)

    def _enqueue(self, q: Deque[Tuple[str, Message]], node: str, msg: Message):
        q.append((node, msg))

    def _apply_overrides(self, agent_name: str, res: Result):
        if res.overrides:
            self.run_overrides[agent_name].update(res.overrides)

    def _next_nodes(self, current: str) -> List[str]:
        return self.graph.get(current, [])

    def run_workflow(self, entry: str, input_data: Any) -> List[Result]:
        results: List[Result] = []
        q: Deque[Tuple[str, Message]] = deque()
        self.state.clear()
        self.run_overrides.clear()

        # Raiz disponível a todos
        self._enqueue(q, entry, Message(data=input_data, meta={"root": input_data, "iteration": 0}))

        while q:
            node, msg = q.popleft()
            agent = self.agents.get(node)
            if not agent:
                raise WorkflowError(f"Agent '{node}' not found")

            # JOIN (aguarda N entradas se necessário)
            ns = self.state[node]
            ns.expected_inputs = max(ns.expected_inputs, int(msg.meta.get("expected_inputs", 1)))
            ns.received.append(msg)
            if len(ns.received) < ns.expected_inputs:
                continue

            payload = self._merge_messages(ns.received)
            ns.received.clear()

            # Executa agente
            res = agent.execute(payload)
            results.append(res)
            ns.last_producer = payload.meta.get("last_producer")

            # Guarda overrides (prompts/model_config futuros)
            self._apply_overrides(node, res)

            ctrl = res.control or {}
            if ctrl.get("halt"):
                break

            next_nodes = self._next_nodes(node)

            # ---------- repeat: reexecuta o PRODUTOR anterior ----------
            if ctrl.get("repeat"):
                prev = ns.last_producer or node
                root_obj = payload.meta.get("root")
                iteration = int(payload.meta.get("iteration", 0)) + 1

                # A saída que o crítico inspecionou está em 'payload.data'
                # Passamos como 'previous' para o produtor refazer
                repeat_msg = Message(
                    data={"input": root_obj, "previous": payload.data},
                    meta={
                        "last_producer": prev,
                        "root": root_obj,
                        "critic_feedback": res.output,  # feedback estruturado do crítico
                        "critic": node,
                        "iteration": iteration
                    }
                )
                self._enqueue(q, prev, repeat_msg)
                continue

            # ---------- goto: pula para um destino específico ----------
            if ctrl.get("goto"):
                next_nodes = [ctrl["goto"]]

            # ---------- fluxo normal ----------
            root_obj = payload.meta.get("root")
            for nxt in next_nodes:
                self._enqueue(
                    q,
                    nxt,
                    Message(
                        data=res.output,
                        meta={
                            "last_producer": node,
                            "root": root_obj,
                            "iteration": payload.meta.get("iteration", 0)
                        }
                    )
                )

        return results

    @staticmethod
    def _merge_messages(messages: List[Message]) -> Message:
        if len(messages) == 1:
            return messages[0]
        data = [m.data for m in messages]
        root = messages[0].meta.get("root")
        it = messages[0].meta.get("iteration", 0)
        return Message(data=data, meta={"root": root, "iteration": it})
