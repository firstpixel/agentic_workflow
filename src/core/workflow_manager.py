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
    last_producer: Optional[str] = None


class WorkflowManager:
    def __init__(self, graph: Dict[str, List[str]], agents: Dict[str, BaseAgent]):
        self.graph = graph
        self.agents = agents
        self.state: Dict[str, NodeState] = defaultdict(NodeState)
        self.run_overrides: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.in_degree: Dict[str, int] = self._compute_in_degree(graph)

    @staticmethod
    def _compute_in_degree(graph: Dict[str, List[str]]) -> Dict[str, int]:
        indeg: Dict[str, int] = defaultdict(int)
        nodes = set(graph.keys())
        for src, targets in graph.items():
            nodes.update(targets)
            for t in targets:
                indeg[t] += 1
        # nós de entrada podem não aparecer como targets
        for n in nodes:
            indeg.setdefault(n, 0)
        return dict(indeg)

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

        self._enqueue(q, entry, Message(data=input_data, meta={"root": input_data, "iteration": 0}))

        while q:
            node, msg = q.popleft()
            agent = self.agents.get(node)
            if not agent:
                raise WorkflowError(f"Agent '{node}' not found")

            ns = self.state[node]
            ns.expected_inputs = max(ns.expected_inputs, int(msg.meta.get("expected_inputs", 1)))
            ns.received.append(msg)
            if len(ns.received) < ns.expected_inputs:
                continue

            payload = self._merge_messages(ns.received)
            ns.received.clear()

            res = agent.execute(payload)
            results.append(res)
            ns.last_producer = payload.meta.get("last_producer")

            self._apply_overrides(node, res)

            ctrl = res.control or {}
            if ctrl.get("halt"):
                break

            next_nodes = self._next_nodes(node)

            if ctrl.get("repeat"):
                prev = ns.last_producer or node
                root_obj = payload.meta.get("root")
                iteration = int(payload.meta.get("iteration", 0)) + 1
                repeat_msg = Message(
                    data={"input": root_obj, "previous": payload.data},
                    meta={
                        "last_producer": prev,
                        "root": root_obj,
                        "critic_feedback": res.output,
                        "critic": node,
                        "iteration": iteration
                    }
                )
                self._enqueue(q, prev, repeat_msg)
                continue

            if ctrl.get("goto"):
                next_nodes = [ctrl["goto"]]

            root_obj = payload.meta.get("root")
            for nxt in next_nodes:
                # ---- payload por ramo (FanOutAgent) ----
                per_branch_data = res.output.get(nxt) if isinstance(res.output, dict) else None
                data_to_send = per_branch_data if per_branch_data is not None else res.output

                # ---- in_degree -> expected_inputs para o nó de destino ----
                exp = max(1, int(self.in_degree.get(nxt, 1)))

                self._enqueue(
                    q,
                    nxt,
                    Message(
                        data=data_to_send,
                        meta={
                            "last_producer": node,
                            "root": root_obj,
                            "iteration": payload.meta.get("iteration", 0),
                            "expected_inputs": exp
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
