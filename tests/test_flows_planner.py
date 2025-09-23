import types

from src.app.flows_planner import build_planner_flow
from src.core.workflow_manager import WorkflowManager
from src.core.types import Message, Result
from src.core.agent import LLMAgent
from src.core.types import Result as CoreResult


def test_planner_flow_end_to_end(monkeypatch):
    # ---- Monkeypatch LLMAgent.run to return canned Markdown per prompt_file ----
    call_count = {"n": 0}

    def fake_run(self, message):
        call_count["n"] += 1
        pf = (self.config.prompt_file or "").lower()

        if pf.endswith("decomposer.md"):
            md = """### DRAFT TASKS
- [T01] Gather requirements
- [T02] Draft outline

### DEPENDENCIES
T02 <- T01
"""
        elif pf.endswith("summarizer.md"):
            md = """### OVERALL SUMMARY
Scope: Create a short doc.
Constraints: Keep it concise.
Definition of success: Final doc delivered.
"""
        elif pf.endswith("detailer.md"):
            # one generic task block per call is OK for this test
            md = """# Task TXX — Placeholder
## Purpose
Why we do it.

## Inputs
- Input A

## Outputs
- Output A

## Procedure (Intent-level steps)
1. Do X
2. Verify Y

## Acceptance Criteria
- AC1

## Dependencies
- (none)

## Risks & Mitigations
- Risk: none → Mitigation: n/a
"""
        elif pf.endswith("merger.md"):
            md = """### FINAL TASK LIST v1

## Overall Summary
<omitted for test>

## Task Table
| ID  | Title               | Status  | Depends On | Acceptance Criteria (short) |
|-----|---------------------|---------|------------|------------------------------|
| T01 | Gather requirements | pending | —          | Goals documented             |
| T02 | Draft outline       | pending | T01        | Outline complete             |

## Milestones
- M1: T01–T02

## Critical Path
T01 → T02
"""
        elif pf.endswith("evaluator.md"):
            md = """### DECISION
PASS

### EDITS
(none)
"""
        elif pf.endswith("refiner.md"):
            md = """### REFINEMENT RESULT (Plan v2)
Replaced: T02
New: T02a, T02b

### DEPENDENCIES
T02a <- T01
T02b <- T02a

# Task T02a — Split A
...

# Task T02b — Split B
...
"""
        else:
            md = "(noop)"

        return CoreResult.ok(output={"text": md}, display_output="fake-llm")

    monkeypatch.setattr(LLMAgent, "run", fake_run)

    # ---- Build flow with MockExecutor (fail_once=True to test retry path) ----
    graph, agents, node_policies = build_planner_flow(
        executor_agent_name="Executor",
        executor_model_config={"fail_once": True},  # first attempt per task fails, then passes
        retry_limit=2,
        planner_model_config={"executor_agent": "Executor", "temperature": 0.0}
    )

    wm = WorkflowManager(graph=graph, agents=agents, node_policies=node_policies)

    # ---- Run the workflow ----
    results = wm.run_workflow("Planner", {"request": "Write a short doc about Philosophi"})

    # ---- Assertions ----
    # 1) LLMAgent has been called multiple times (decomposer, summarizer, detailer x2, merger, evaluator = 6+)
    assert call_count["n"] >= 6

    # 2) We should have at least one Updater "complete" message
    done_msgs = [r for r in results if isinstance(r.output, dict) and r.output.get("final_md")]
    assert len(done_msgs) >= 1

    final_md = done_msgs[-1].output["final_md"]
    assert "Plan Execution Summary" in final_md

    # 3) No unhandled failure
    failures = [r for r in results if r.success is False]
    assert not failures
