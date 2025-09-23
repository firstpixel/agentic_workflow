from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Deque, Tuple
from collections import deque, defaultdict
import traceback
import time

from .types import Message, Result, WorkflowError
from .agent import BaseAgent
from src.eval.metrics import MetricsCollector  # opcional


@dataclass
class NodeState:
    expected_inputs: int = 1
    received: List[Message] = field(default_factory=list)
    last_producer: Optional[str] = None
    attempts: int = 0  # retry counter for the *current* execution window
    retry_history: List[Dict[str, Any]] = field(default_factory=list)  # persisted per-run retry log


class WorkflowManager:
    def __init__(
        self,
        graph: Dict[str, List[str]],
        agents: Dict[str, BaseAgent],
        metrics: Optional[MetricsCollector] = None,
        node_policies: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """
        node_policies (optional) example:
        {
            "Author": {"max_retries": 2, "on_error": "FallbackAuthor", "retry_on_failure": True},
            "Fetcher": {"max_retries": 1}
        }

        Keys:
          - max_retries: int  (default 0) → for both exceptions AND failed results
          - on_error: Optional[str] → fallback node name
          - retry_on_failure: bool (default False) → whether Result.success=False triggers retries
        """
        self.graph = graph
        self.agents = agents
        self.state: Dict[str, NodeState] = defaultdict(NodeState)
        self.run_overrides: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.in_degree: Dict[str, int] = self._compute_in_degree(graph)
        self.metrics = metrics
        self.node_policies = node_policies or {}

    @staticmethod
    def _compute_in_degree(graph: Dict[str, List[str]]) -> Dict[str, int]:
        indeg: Dict[str, int] = defaultdict(int)
        nodes = set(graph.keys())
        for _, targets in graph.items():
            nodes.update(targets)
            for t in targets:
                indeg[t] += 1
        for n in nodes:
            indeg.setdefault(n, 0)
        return dict(indeg)

    def _enqueue(self, q: Deque[Tuple[str, Message]], node: str, msg: Message):
        q.append((node, msg))

    def _policy_for(self, node: str) -> Dict[str, Any]:
        """
        Returns safe per-node policy with conservative defaults for backward compatibility.
        """
        pol = (self.node_policies.get(node, {}) or {}).copy()
        pol.setdefault("max_retries", 0)
        pol.setdefault("on_error", None)
        pol.setdefault("retry_on_failure", False)  # keep old behavior unless explicitly enabled
        return pol

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

    def _record_retry_event(
        self,
        node: str,
        ns: NodeState,
        event_type: str,
        details: Dict[str, Any],
    ):
        """
        Persist retry/fallback timeline in NodeState and notify metrics if present.
        event_type: "exception" | "failed_result" | "retry_enqueued" | "fallback"
        """
        entry = {
            "ts": time.time(),
            "event": event_type,
            "attempt": ns.attempts,
            **details,
        }
        ns.retry_history.append(entry)

        # optional external sink via metrics
        if self.metrics and hasattr(self.metrics, "on_retry_node"):
            try:
                self.metrics.on_retry_node(node, entry)
            except Exception:
                # never let observability break the flow
                pass

    def _record_fallback_metrics(self, node: str, info: Dict[str, Any]):
        if self.metrics and hasattr(self.metrics, "on_fallback_node"):
            try:
                self.metrics.on_fallback_node(node, info)
            except Exception:
                pass

    def get_retry_history(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Expose per-node retry history for this run.
        """
        return {n: st.retry_history[:] for n, st in self.state.items() if st.retry_history}

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

            # Apply overrides targeted to *this* node
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

            pol = self._policy_for(node)

            try:
                res = agent.execute(payload)
                results.append(res)  # keep previous behavior: collect every Result
                ns.last_producer = payload.meta.get("last_producer")

                if self.metrics:
                    self.metrics.on_end_node(node, {
                        "success": res.success,
                        "metrics": res.metrics,
                        "control": res.control,
                        "output": res.output
                    })

                # Handle success==False as retryable (policy-controlled)
                should_retry_for_failure = (
                    res is not None and
                    res.success is False and
                    pol.get("retry_on_failure", False) and
                    not (res.control or {})  # if control signals exist, respect them (back-compat)
                )

                if should_retry_for_failure:
                    ns.attempts += 1
                    # log failure event
                    self._record_retry_event(
                        node,
                        ns,
                        event_type="failed_result",
                        details={
                            "max_retries": pol.get("max_retries", 0),
                            "reason": res.metrics or {"note": "Result.success=False"},
                        },
                    )
                    if ns.attempts <= int(pol.get("max_retries", 0)):
                        root_obj = payload.meta.get("root")
                        retry_msg = Message(
                            data=payload.data,
                            meta={
                                "last_producer": payload.meta.get("last_producer"),
                                "root": root_obj,
                                "iteration": payload.meta.get("iteration", 0),
                                "expected_inputs": 1,  # do not re-wait for join
                                "retry": ns.attempts,
                                "retry_reason": "failed_result"
                            }
                        )
                        self._record_retry_event(node, ns, "retry_enqueued", {"to": node})
                        self._enqueue(q, node, retry_msg)
                        continue
                    # retries exhausted → fallback or error
                    on_error = pol.get("on_error")
                    if on_error:
                        root_obj = payload.meta.get("root")
                        exp = max(1, int(self.in_degree.get(on_error, 1)))
                        fb_payload = {
                            "error": {
                                "message": "Result.success=False (retries exhausted)",
                                "type": "FailedResult",
                                "traceback": None
                            },
                            "failed_node": node,
                            "input": payload.data,
                            "last_result": res.output
                        }
                        self._record_retry_event(node, ns, "fallback", {"to": on_error, "info": fb_payload["error"]})
                        self._record_fallback_metrics(node, {"to": on_error, "reason": "failed_result_retries_exhausted"})
                        ns.attempts = 0
                        self._enqueue(
                            q,
                            on_error,
                            Message(
                                data=fb_payload,
                                meta={
                                    "last_producer": node,
                                    "root": root_obj,
                                    "iteration": payload.meta.get("iteration", 0),
                                    "expected_inputs": exp
                                }
                            )
                        )
                        continue
                    # no fallback configured
                    raise WorkflowError(f"Agent '{node}' returned success=False after {ns.attempts} retries")

                # Normal (non-retry) control flow continues below
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

                # success path → reset attempts
                ns.attempts = 0

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
                            meta={
                                "last_producer": node,
                                "root": root_obj,
                                "iteration": payload.meta.get("iteration", 0),
                                "expected_inputs": exp
                            }
                        )
                    )

            except Exception as e:
                # --- Retry & fallback for exceptions (unchanged logic, now with history) ---
                ns.attempts += 1
                tb = traceback.format_exc()

                # record exception event
                self._record_retry_event(
                    node,
                    ns,
                    event_type="exception",
                    details={
                        "max_retries": self._policy_for(node).get("max_retries", 0),
                        "error": str(e),
                        "exc_type": e.__class__.__name__,
                    },
                )

                if self.metrics and hasattr(self.metrics, "on_error_node"):
                    try:
                        self.metrics.on_error_node(node, {
                            "attempt": ns.attempts,
                            "max_retries": self._policy_for(node).get("max_retries", 0),
                            "error": str(e)
                        })
                    except Exception:
                        pass

                if ns.attempts <= int(self._policy_for(node).get("max_retries", 0)):
                    root_obj = payload.meta.get("root")
                    retry_msg = Message(
                        data=payload.data,
                        meta={
                            "last_producer": payload.meta.get("last_producer"),
                            "root": root_obj,
                            "iteration": payload.meta.get("iteration", 0),
                            "expected_inputs": 1,
                            "retry": ns.attempts,
                            "retry_reason": "exception"
                        }
                    )
                    self._record_retry_event(node, ns, "retry_enqueued", {"to": node})
                    self._enqueue(q, node, retry_msg)
                    continue

                on_error = self._policy_for(node).get("on_error")
                if on_error:
                    root_obj = payload.meta.get("root")
                    exp = max(1, int(self.in_degree.get(on_error, 1)))
                    fb_payload = {
                        "error": {
                            "message": str(e),
                            "type": e.__class__.__name__,
                            "traceback": tb
                        },
                        "failed_node": node,
                        "input": payload.data
                    }
                    self._record_retry_event(node, ns, "fallback", {"to": on_error, "info": fb_payload["error"]})
                    self._record_fallback_metrics(node, {"to": on_error, "reason": "exception_retries_exhausted"})
                    ns.attempts = 0
                    self._enqueue(
                        q,
                        on_error,
                        Message(
                            data=fb_payload,
                            meta={
                                "last_producer": node,
                                "root": root_obj,
                                "iteration": payload.meta.get("iteration", 0),
                                "expected_inputs": exp
                            }
                        )
                    )
                    continue

                raise WorkflowError(f"Agent '{node}' failed after {ns.attempts} attempt(s): {e}") from e

        # Emit final retry history snapshot to metrics if supported
        if self.metrics and hasattr(self.metrics, "on_retry_history_complete"):
            try:
                self.metrics.on_retry_history_complete(self.get_retry_history())
            except Exception:
                pass

        return results

    async def route_message(self, message_data: Dict[str, Any], target_agent: str) -> Dict[str, Any]:
        """
        Route a message directly to a specific agent for Updater coordination.
        
        Args:
            message_data: The message data to send
            target_agent: The target agent name
            
        Returns:
            Result from the target agent
        """
        if target_agent not in self.agents:
            return {"success": False, "error": f"Agent {target_agent} not found"}
        
        try:
            message = Message(data=message_data, meta={"source": "updater"})
            agent = self.agents[target_agent]
            
            # Apply any pending overrides
            overrides = self.run_overrides.get(target_agent, {})
            
            result = await agent.process(message, **overrides)
            
            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "overrides": result.overrides
            }
            
        except Exception as e:
            return {
                "success": False, 
                "error": f"Exception in {target_agent}: {str(e)}"
            }

    @staticmethod
    def _merge_messages(messages: List[Message]) -> Message:
        if len(messages) == 1:
            return messages[0]
        data = [m.data for m in messages]
        root = messages[0].meta.get("root")
        it = messages[0].meta.get("iteration", 0)
        return Message(data=data, meta={"root": root, "iteration": it})
