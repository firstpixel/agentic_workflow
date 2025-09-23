# src/app/flows_retries.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from src.core.workflow_manager import WorkflowManager
from src.core.types import Message, Result
from src.core.agent import BaseAgent, AgentConfig
from src.eval.metrics import MetricsCollector
from src.agents.join_agent import JoinAgent  # reuse your real JoinAgent

# ---------- Helper demo agents (minimal, SRP) ----------

class StartAgent(BaseAgent):
    """Emits per-branch payloads to fan out."""
    def __init__(self, cfg: Optional[AgentConfig] = None):
        self.config = cfg or AgentConfig(name="Start")

    def execute(self, payload: Message) -> Result:
        return Result(
            success=True,
            output={
                "Exc": {"seed": "exc-seed"},
                "Fail": {"seed": "fail-seed"},
                "FailHard": {"seed": "hard-fail-seed"}
            },
            control={},
            metrics={"agent": "Start"}
        )


class FlakyExceptionAgent(BaseAgent):
    """Raises an exception `fail_times` times, then succeeds."""
    def __init__(self, fail_times: int = 1, cfg: Optional[AgentConfig] = None):
        self.config = cfg or AgentConfig(name="Exc")
        self.fail_times = fail_times
        self.calls = 0

    def execute(self, payload: Message) -> Result:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"{self.config.name} boom on call {self.calls}")
        return Result(
            success=True,
            output={"agent": self.config.name, "status": "ok-after-exception", "calls": self.calls},
            control={},
            metrics={"agent": self.config.name, "calls": self.calls}
        )


class FlakyFailureAgent(BaseAgent):
    """Returns success=False `fail_times` times, then succeeds."""
    def __init__(self, name: str = "Fail", fail_times: int = 1, cfg: Optional[AgentConfig] = None):
        self.config = cfg or AgentConfig(name=name)
        self.fail_times = fail_times
        self.calls = 0

    def execute(self, payload: Message) -> Result:
        self.calls += 1
        if self.calls <= self.fail_times:
            return Result(
                success=False,
                output={"agent": self.config.name, "status": "not-good-yet", "calls": self.calls},
                control={},  # respect policies for retry_on_failure
                metrics={"reason": "quality_fail", "calls": self.calls}
            )
        return Result(
            success=True,
            output={"agent": self.config.name, "status": "ok-after-failure", "calls": self.calls},
            control={},
            metrics={"agent": self.config.name, "calls": self.calls}
        )


class FallbackAgent(BaseAgent):
    """Handles fallback payload from a failing node."""
    def __init__(self, cfg: Optional[AgentConfig] = None):
        self.config = cfg or AgentConfig(name="Fallback")

    def execute(self, payload: Message) -> Result:
        err = payload.data.get("error", {})
        return Result(
            success=True,
            output={
                "agent": self.config.name,
                "handled_error_type": err.get("type"),
                "from_node": payload.data.get("failed_node")
            },
            control={},
            metrics={"agent": self.config.name}
        )


class TerminalAgent(BaseAgent):
    """Final sink—normalizes input to a list so we can inspect batches."""
    def __init__(self, cfg: Optional[AgentConfig] = None):
        self.config = cfg or AgentConfig(name="Terminal")

    def execute(self, payload: Message) -> Result:
        data = payload.data if isinstance(payload.data, list) else [payload.data]
        return Result(
            success=True,
            output={"agent": self.config.name, "final_batch": data},
            control={},
            metrics={"agent": self.config.name, "received": len(data)}
        )


# ---------- Optional: pretty metrics for console demo ----------

class DemoMetrics(MetricsCollector):
    def on_start_node(self, node: str):
        print(f"▶️  Start: {node}")

    def on_end_node(self, node: str, info: Dict[str, Any]):
        ok = "✅" if info.get("success") else "⚠️ "
        print(f"{ok} End: {node} | metrics={info.get('metrics')} control={info.get('control')}")

    def on_error_node(self, node: str, info: Dict[str, Any]):
        print(f"❌ Error@{node} attempt={info.get('attempt')}/{info.get('max_retries')} err={info.get('error')}")

    def on_retry_node(self, node: str, entry: Dict[str, Any]):
        print(f"🔁 RetryEvent@{node}: {entry}")

    def on_fallback_node(self, node: str, info: Dict[str, Any]):
        print(f"🛟 Fallback from {node} → {info.get('to')} | reason={info.get('reason')}")

    def on_retry_history_complete(self, history: Dict[str, List[Dict[str, Any]]]):
        print("\n📜 Retry History (per node):")
        for n, events in history.items():
            print(f"  - {n}:")
            for e in events:
                print(f"      {e}")


# ---------- Flow bundle ----------

@dataclass
class FlowBundle:
    graph: Dict[str, List[str]]
    agents: Dict[str, BaseAgent]
    node_policies: Dict[str, Dict[str, Any]]

    def manager(self, metrics: Optional[MetricsCollector] = None) -> WorkflowManager:
        return WorkflowManager(
            graph=self.graph,
            agents=self.agents,
            metrics=metrics,
            node_policies=self.node_policies
        )


def make_retries_fallback_flow(
    exc_fail_times: int = 1,
    fail_fail_times: int = 1,
    failhard_fail_times: int = 3,
    exc_retries: int = 2,
    fail_retries: int = 2,
    failhard_retries: int = 1,
) -> FlowBundle:
    """
    Build a fan-out flow that demonstrates:
      - Retry on exception (Exc)
      - Retry on success=False (Fail)
      - Fallback after retries exhausted (FailHard → Fallback)
      - Fan-in via Join → Terminal
    """
    graph = {
        "Start": ["Exc", "Fail", "FailHard"],
        "Exc": ["Join"],
        "Fail": ["Join"],
        "FailHard": [],          # fallback edge handled via node_policies on error
        "Join": ["Terminal"],
        "Fallback": ["Terminal"],
        "Terminal": []
    }

    agents = {
        "Start": StartAgent(),
        "Exc": FlakyExceptionAgent(fail_times=exc_fail_times, cfg=AgentConfig(name="Exc")),
        "Fail": FlakyFailureAgent(name="Fail", fail_times=fail_fail_times, cfg=AgentConfig(name="Fail")),
        "FailHard": FlakyFailureAgent(name="FailHard", fail_times=failhard_fail_times, cfg=AgentConfig(name="FailHard")),
        "Join": JoinAgent(AgentConfig(name="Join")),
        "Fallback": FallbackAgent(AgentConfig(name="Fallback")),
        "Terminal": TerminalAgent(AgentConfig(name="Terminal")),
    }

    node_policies = {
        "Exc": {"max_retries": exc_retries},
        "Fail": {"max_retries": fail_retries, "retry_on_failure": True},
        "FailHard": {"max_retries": failhard_retries, "retry_on_failure": True, "on_error": "Fallback"},
    }

    return FlowBundle(graph=graph, agents=agents, node_policies=node_policies)


# ---------- Convenience runner for main.py ----------

def run_retries_fallback_demo():
    print("\n" + "=" * 60)
    print("🧪 DEMO — Retries (exception & failed result) + Fallback + Retry History")
    print("=" * 60)

    fb = make_retries_fallback_flow()
    wm = fb.manager(metrics=DemoMetrics())

    results = wm.run_workflow("Start", {"request": "demo-retries"})
    history = wm.get_retry_history()

    finals = [r for r in results if isinstance(r.output, dict) and r.output.get("agent") == "Terminal"]
    print("\n✅ Demo complete. Terminal outputs:")
    for i, r in enumerate(finals, 1):
        print(f"  Terminal[{i}]: {r.output}")

    print("\nRetry history (counts):")
    for node, events in history.items():
        print(f"  {node}: {len(events)} event(s)")
