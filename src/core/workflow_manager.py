from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Deque, Tuple
from collections import deque, defaultdict

from .types import Message, Result, WorkflowError
from .agent import BaseAgent


@dataclass
class NodeState:
    """Holds per-node accumulators for join patterns, last producer, etc."""
    expected_inputs: int = 1
    received: List[Message] = field(default_factory=list)
    last_producer: Optional[str] = None   # for control.repeat


class WorkflowManager:
    """
    Very simple graph runner:
    - graph: dict[str, list[str]] mapping node -> next_nodes
    - agents: dict[str, BaseAgent]
    - respects control flags: goto, repeat, halt
    """
    def __init__(self, graph: Dict[str, List[str]], agents: Dict[str, BaseAgent]):
        self.graph = graph
        self.agents = agents
        self.state: Dict[str, NodeState] = defaultdict(NodeState)
        # Optional per-run stores (T8 metrics, T10 prompts, T9 model overrides)
        self.run_overrides: Dict[str, Dict[str, Any]] = defaultdict(dict)

    def _enqueue(self, q: Deque[Tuple[str, Message]], node: str, msg: Message):
        q.append((node, msg))

    def _apply_overrides(self, agent_name: str, res: Result):
        """Store overrides (prompt/model_config) for downstream agents (T9/T10)."""
        if res.overrides:
            self.run_overrides[agent_name].update(res.overrides)

    def _next_nodes(self, current: str) -> List[str]:
        return self.graph.get(current, [])

    def run_workflow(self, entry: str, input_data: Any) -> List[Result]:
        """
        Executes the graph from 'entry' with a given input.
        Returns the list of all Results (in run order).
        """
        results: List[Result] = []
        q: Deque[Tuple[str, Message]] = deque()
        self.state.clear()
        self.run_overrides.clear()

        self._enqueue(q, entry, Message(data=input_data))

        while q:
            node, msg = q.popleft()
            agent = self.agents.get(node)
            if not agent:
                raise WorkflowError(f"Agent '{node}' not found")

            # Apply prompt/model overrides from previous nodes (T9/T10)
            overrides = self.run_overrides.get(node, {})
            if overrides.get("model_config"):
                agent.config.model_config.update(overrides["model_config"])
            if overrides.get("prompt") and hasattr(agent.config, "prompt"):
                agent.config.prompt = overrides["prompt"]

            # SUPPORT FOR JOIN (expected_inputs > 1)
            ns = self.state[node]
            ns.expected_inputs = max(ns.expected_inputs, int(msg.meta.get("expected_inputs", 1)))
            ns.received.append(msg)
            if len(ns.received) < ns.expected_inputs:
                # Wait for remaining inputs before actually running the node
                continue

            # Merge payloads for the node if multiple inputs
            payload = self._merge_messages(ns.received)
            ns.received.clear()

            # Execute
            res = agent.execute(payload)
            results.append(res)
            ns.last_producer = payload.meta.get("last_producer")

            # Store any overrides for downstream nodes
            self._apply_overrides(node, res)

            # CONTROL FLAGS: halt / goto / repeat
            ctrl = res.control or {}
            if ctrl.get("halt"):
                break

            next_nodes = self._next_nodes(node)

            # repeat: re-enqueue the last producer agent (if known) with same data
            if ctrl.get("repeat"):
                prev = ns.last_producer or node  # fallback to self
                self._enqueue(q, prev, Message(data=payload.data, meta={"last_producer": prev}))
                continue

            # goto: override next_nodes with a single jump target
            if ctrl.get("goto"):
                next_nodes = [ctrl["goto"]]

            # Enqueue downstream nodes
            for nxt in next_nodes:
                # pass 'last_producer' for potential repeat loops
                self._enqueue(q, nxt, Message(data=res.output, meta={"last_producer": node}))

        return results

    @staticmethod
    def _merge_messages(messages: List[Message]) -> Message:
        """Simple merge: produce a list when multiple inputs arrive."""
        if len(messages) == 1:
            return messages[0]
        data = [m.data for m in messages]
        meta = {}
        return Message(data=data, meta=meta)
