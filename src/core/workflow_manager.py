from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Deque, Tuple
from collections import deque, defaultdict

from .types import Message, Result, WorkflowError
from .agent import BaseAgent
from src.eval.metrics import MetricsCollector  # opcional


@dataclass
class NodeState:
    expected_inputs: int = 1
    received: List[Message] = field(default_factory=list)
    last_producer: Optional[str] = None


class WorkflowManager:
    def __init__(self, graph: Dict[str, List[str]], agents: Dict[str, BaseAgent],
                 metrics: Optional[MetricsCollector] = None):
        self.graph = graph
        self.agents = agents
        self.state: Dict[str, NodeState] = defaultdict(NodeState)
        self.run_overrides: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.in_degree: Dict[str, int] = self._compute_in_degree(graph)
        self.metrics = metrics

    @staticmethod
    def _compute_in_degree(graph: Dict[str, List[str]]) -> Dict[str, int]:
        indeg: Dict[str, int] = defaultdict(int)
        nodes = set(graph.keys())
        for src, targets in graph.items():
            nodes.update(targets)
            for t in targets:
                indeg[t] += 1
        for n in nodes:
            indeg.setdefault(n, 0)
        return dict(indeg)

    def _enqueue(self, q: Deque[Tuple[str, Message]], node: str, msg: Message):
        q.append((node, msg))

    def _apply_overrides(self, agent_name: str, res: Result):
        """Store overrides (prompt/model_config).
        Supports two styles:
          1) legacy: res.overrides has direct keys for the same agent (applied when this agent runs again)
          2) targeted: res.overrides['for'] = { '<TargetAgent>': {'model_config': {...}, 'prompt_file': '...'} }
             These are applied when the *target* agent runs.
        """
        if not res.overrides:
            return
        # legacy behavior (keep it)
        direct_mc = res.overrides.get("model_config")
        direct_pf = res.overrides.get("prompt_file")
        if direct_mc or direct_pf:
            current = self.run_overrides.get(agent_name, {})
            if direct_mc:
                current.setdefault("model_config", {}).update(direct_mc)
            if direct_pf:
                current["prompt_file"] = direct_pf
            self.run_overrides[agent_name] = current

        # targeted behavior
        targeted = res.overrides.get("for")
        if isinstance(targeted, dict):
            for tgt, cfg in targeted.items():
                if not isinstance(cfg, dict):
                    continue
                cur = self.run_overrides.get(tgt, {})
                if "model_config" in cfg and isinstance(cfg["model_config"], dict):
                    cur.setdefault("model_config", {}).update(cfg["model_config"])
                if "prompt_file" in cfg and isinstance(cfg["prompt_file"], str):
                    cur["prompt_file"] = cfg["prompt_file"]
                self.run_overrides[tgt] = cur

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

            if self.metrics:
                self.metrics.on_start_node(node)

            # Apply prompt/model overrides targeted to *this* node (T9)
            overrides = self.run_overrides.get(node, {})
            if overrides.get("model_config"):
                agent.config.model_config.update(overrides["model_config"])
            # prefer 'prompt_file' (markdown prompt path) over old 'prompt'
            if overrides.get("prompt_file"):
                agent.config.prompt_file = overrides["prompt_file"]
            elif overrides.get("prompt") and hasattr(agent.config, "prompt"):
                agent.config.prompt = overrides["prompt"]

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

            if self.metrics:
                # serializa uma visão do Result p/ registro
                self.metrics.on_end_node(node, {
                    "success": res.success,
                    "metrics": res.metrics,
                    "control": res.control,
                    "output": res.output
                })

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
                per_branch_data = res.output.get(nxt) if isinstance(res.output, dict) else None
                data_to_send = per_branch_data if per_branch_data is not None else res.output
                exp = max(1, int(self.in_degree.get(nxt, 1)))
                self._enqueue(
                    q,
                    nxt,
                    Message(
                        data=data_to_send,
                        meta={"last_producer": node, "root": root_obj, "iteration": payload.meta.get("iteration", 0), "expected_inputs": exp}
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
