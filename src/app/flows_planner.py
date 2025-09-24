from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import re
from dataclasses import dataclass

from src.core.agent import BaseAgent, AgentConfig, LLMAgent
from src.core.types import Message, Result
from src.core.workflow_manager import WorkflowManager
from src.agents.planner_agent import PlannerAgent


# ===========================
# Helpers: parse a task block
# ===========================
_TASK_ID = re.compile(r"^#\s*Task\s+(?P<id>[A-Za-z0-9_.\-]+)\s*—\s*(?P<title>.+)$", re.MULTILINE)

def _find_task_block(tasks_md: List[str], task_id: str) -> Optional[str]:
    for block in tasks_md:
        m = _TASK_ID.search(block)
        if m and m.group("id").strip() == task_id:
            return block
    return None


# ===========================
# UpdaterAgent (sequential)
# ===========================
class UpdaterAgent(BaseAgent):
    """
    One-by-one task loop. Tracks retries and escalates to Planner with a REFINE REQUEST.
    model_config:
      retry_limit: int = 2
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)

    def run(self, message: Message) -> Result:
        data = message.data or {}
        mc = self.config.model_config or {}
        retry_limit = int(mc.get("retry_limit", 2))

        # First call after Planner
        if "plan_meta" in data and "tasks_md" in data:
            plan_state = {
                "summary_md": data.get("summary_md", ""),
                "final_plan_md": data.get("final_plan_md", ""),
                "tasks_md": data.get("tasks_md", []),
                "task_ids": list(data.get("plan_meta", {}).get("task_ids", [])),
                "dag_edges": list(data.get("plan_meta", {}).get("dag_edges", [])),
                "executor_agent": data.get("plan_meta", {}).get("executor_agent", "Executor"),
                "status": {tid: {"status": "pending", "retries": 0} for tid in data.get("plan_meta", {}).get("task_ids", [])}
            }
            next_id = self._next_ready(plan_state)
            if not next_id:
                return Result.ok(output={"plan_state": plan_state, "message": "No tasks to execute"}, display_output="✅ Updater: nothing to do")
            task_block = _find_task_block(plan_state["tasks_md"], next_id) or f"# Task {next_id} — (missing)"
            return Result.ok(
                output={"executor_payload": {"task_id": next_id, "task_md": task_block, "plan_state": plan_state}},
                display_output=f"📤 Updater→Executor: {next_id}",
                control={"goto": plan_state["executor_agent"]}  # route to selected executor
            )

        # Back from Executor
        if "task_id" in data and "success" in data and "plan_state" in data:
            ps = data["plan_state"]
            tid = data["task_id"]
            succ = bool(data["success"])

            entry = ps["status"].setdefault(tid, {"status": "pending", "retries": 0})
            if succ:
                entry["status"] = "done"
            else:
                entry["retries"] = entry.get("retries", 0) + 1
                entry["status"] = "pending"

            # Escalate for refinement
            if not succ and entry["retries"] >= retry_limit:
                refine_md = self._refine_request_md(tid, data.get("evidence_md", ""), ps)
                return Result.ok(
                    output={"refine_request_md": refine_md},
                    display_output=f"🆘 Updater→Planner refine {tid}",
                    control={"goto": "Planner"}
                )

            # Next task (or retry same if it becomes "next")
            next_id = self._next_ready(ps)
            if not next_id:
                final_md = self._final_summary_md(ps)
                return Result.ok(
                    output={"final_md": final_md, "plan_state": ps},
                    display_output="🏁 Updater: plan complete"
                )

            task_block = _find_task_block(ps["tasks_md"], next_id) or f"# Task {next_id} — (missing)"
            return Result.ok(
                output={"executor_payload": {"task_id": next_id, "task_md": task_block, "plan_state": ps}},
                display_output=f"📤 Updater→Executor: {next_id}",
                control={"goto": ps["executor_agent"]}
            )

        return Result.ok(output={"echo": data}, display_output="ℹ️ Updater: noop")

    # ---- helpers ----
    def _deps_done(self, ps: Dict[str, Any], tid: str) -> bool:
        # edges like "T02 <- T01"
        for line in ps.get("dag_edges", []):
            parts = [x.strip() for x in line.split("<-")]
            if len(parts) != 2:
                continue
            to, frm = parts[0], parts[1]
            if to == tid and ps["status"].get(frm, {}).get("status") != "done":
                return False
        return True

    def _next_ready(self, ps: Dict[str, Any]) -> Optional[str]:
        for tid in ps.get("task_ids", []):
            st = ps["status"].get(tid, {}).get("status", "pending")
            if st != "done" and self._deps_done(ps, tid):
                return tid
        return None

    def _refine_request_md(self, tid: str, evidence_md: str, ps: Dict[str, Any]) -> str:
        return f"""### REFINE REQUEST
- Task: {tid}
- Reason: exceeded retry limit
- Evidence:
{evidence_md or "(none)"}
- Ask: split {tid} into smaller atomic tasks (≤ 2h) with precise Acceptance Criteria.
"""

    def _final_summary_md(self, ps: Dict[str, Any]) -> str:
        done = [tid for tid, s in ps["status"].items() if s.get("status") == "done"]
        pending = [tid for tid, s in ps["status"].items() if s.get("status") != "done"]
        return f"""# Plan Execution Summary
- Done: {', '.join(done) or '(none)'}
- Pending: {', '.join(pending) or '(none)'}
"""


# ===========================
# MockExecutorAgent (for demo)
# ===========================
class MockExecutorAgent(BaseAgent):
    """
    Deterministic mocked executor.
    model_config:
      fail_once: bool = False
      always_fail: bool = False
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self._seen: Dict[str, int] = {}

    def run(self, message: Message) -> Result:
        payload = message.data or {}
        xp = payload.get("executor_payload") or {}
        tid = xp.get("task_id")
        ps = xp.get("plan_state", {})
        evidence = f"Mock execution evidence for {tid}"

        mc = self.config.model_config or {}
        always_fail = bool(mc.get("always_fail", False))
        fail_once   = bool(mc.get("fail_once", False))

        if always_fail:
            succ = False
        elif fail_once:
            c = self._seen.get(tid, 0)
            succ = (c >= 1)
            self._seen[tid] = c + 1
        else:
            succ = True

        out = {"task_id": tid, "success": succ, "evidence_md": f"- {evidence}", "plan_state": ps}
        return Result.ok(output=out, display_output=f"🧪 MockExecutor {tid}: {'OK' if succ else 'FAIL'}")


# ===========================
# Builder (for production use)
# ===========================
def build_planner_flow(
    executor_agent_name: str = "Executor",
    executor_model_config: Optional[Dict[str, Any]] = None,
    retry_limit: int = 2,
    planner_model_config: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, List[str]], Dict[str, BaseAgent], Dict[str, Dict[str, Any]]]:
    """
    Returns (graph, agents, node_policies) for WorkflowManager.
    Graph: Planner → Updater, Executor → Updater
    """
    planner = PlannerAgent(AgentConfig(
        name="Planner",
        prompt_file="",  # stages load their own prompt files via LLMAgent
        model_config=(planner_model_config or {})
    ))

    updater = UpdaterAgent(AgentConfig(
        name="Updater",
        prompt_file="updater.md",
        model_config={"retry_limit": retry_limit}
    ))

    executor = MockExecutorAgent(AgentConfig(
        name=executor_agent_name,
        prompt_file=f"{executor_agent_name}.md",
        model_config=(executor_model_config or {})
    ))

    graph = {"Planner": ["Updater"], "Updater": [executor_agent_name]}
    agents = {"Planner": planner, "Updater": updater, executor_agent_name: executor}
    node_policies: Dict[str, Dict[str, Any]] = {}
    return graph, agents, node_policies


# ===========================
# Self-contained demo
# ===========================
def demo_planner() -> None:
    """
    Self-contained demo:
      - Uses real LLM calls for PlannerAgent stages (Ollama)
      - MockExecutorAgent simulates task execution
      - Builds Planner + Updater + MockExecutor flow
      - Runs WorkflowManager from 'Planner' with a sample request
      - Prints a readable summary
    """
    import os
    
    # No monkeypatch - use real LLM calls for planner stages
    
    # --- Build the flow with a mocked executor only ---
    graph, agents, node_policies = build_planner_flow(
        executor_agent_name="Executor",
        executor_model_config={"fail_once": True},  # show one retry per task
        retry_limit=2,
        planner_model_config={
            "executor_agent": "Executor",
            "model": os.getenv("OLLAMA_MODEL", "gemma3:latest"),
            "options": {"temperature": 0.0}  # carried into LLMAgent stage configs
        }
    )

    wm = WorkflowManager(graph=graph, agents=agents, node_policies=node_policies)

    # --- Run the demo ---
    print("\n" + "="*60)
    print("🧭 Planner Flow Demo (self-contained)")
    print("="*60)

    results = wm.run_workflow("Planner", {
        "request": "Build a React page that loads and displays ArXiv AI papers from https://export.arxiv.org/api/query?search_query=all:csai&start=0&max_results=10 API, showing paper titles, authors, abstracts, and links to PDF downloads"
    })

    # --- Pretty-print highlights ---
    final_msgs = [r for r in results if isinstance(r.output, dict) and r.output.get("final_md")]
    if final_msgs:
        print("\n" + "-"*60)
        print("🏁 FINAL SUMMARY")
        print("-"*60)
        print(final_msgs[-1].output["final_md"])

    planner_outs = [r for r in results if isinstance(r.output, dict) and r.output.get("final_plan_md")]
    if planner_outs:
        print("\n" + "-"*60)
        print("📝 FINAL PLAN (Planner)")
        print("-"*60)
        print(planner_outs[-1].output["final_plan_md"])

    # Show retry history if WorkflowManager collected it
    try:
        rh = wm.get_retry_history()
        if rh:
            import pprint
            print("\n" + "-"*60)
            print("🔁 RETRY HISTORY")
            print("-"*60)
            pprint.pprint(rh)
    except Exception:
        pass

    print("\n✅ Demo finished.\n")


# Allow running this module directly
if __name__ == "__main__":
    demo_planner()
