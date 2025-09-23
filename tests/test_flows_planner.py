import os
from src.app.flows_planner import build_planner_flow
from src.core.workflow_manager import WorkflowManager


def test_planner_flow_end_to_end():
    """Test the full planner flow using real Ollama calls"""
    
    # ---- Build flow with MockExecutor (fail_once=True to test retry path) ----
    graph, agents, node_policies = build_planner_flow(
        executor_agent_name="Executor",
        executor_model_config={"fail_once": True},  # first attempt per task fails, then passes
        retry_limit=2,
        planner_model_config={
            "executor_agent": "Executor", 
            "model": os.getenv("OLLAMA_MODEL", "gemma2:2b"),
            "options": {"temperature": 0.1}
        }
    )

    wm = WorkflowManager(graph=graph, agents=agents, node_policies=node_policies)

    # ---- Run the workflow ----
    print("\n" + "="*60)
    print("🧭 Testing Planner Flow with Real Ollama Calls")
    print("="*60)
    
    results = wm.run_workflow("Planner", {
        "request": "Create a simple Python script that reads a CSV file and prints the first 5 rows"
    })

    # ---- Print results for debugging ----
    print(f"\n📊 Workflow Results Summary:")
    print(f"Total results: {len(results)}")
    
    for i, result in enumerate(results):
        print(f"\nResult {i+1}:")
        print(f"  Success: {result.success}")
        print(f"  Display: {result.display_output}")
        if isinstance(result.output, dict):
            print(f"  Output keys: {list(result.output.keys())}")
        
    # ---- Assertions ----
    # 1) Should have successful results
    failures = [r for r in results if r.success is False]
    assert not failures, f"Found {len(failures)} failed results"

    # 2) Should have at least one result from Planner
    planner_results = [r for r in results if isinstance(r.output, dict) and "plan_meta" in r.output]
    assert len(planner_results) >= 1, "Should have at least one planner result with plan_meta"

    # 3) Should have either a final summary or task execution results
    final_msgs = [r for r in results if isinstance(r.output, dict) and r.output.get("final_md")]
    executor_msgs = [r for r in results if isinstance(r.output, dict) and "executor_payload" in r.output]
    
    # The flow should either complete fully (final_md) or at least start execution (executor_payload)
    assert len(final_msgs) >= 1 or len(executor_msgs) >= 1, "Should have either final summary or task execution"
    
    # 4) Verify plan structure if we have planner output
    if planner_results:
        plan_output = planner_results[-1].output
        assert "plan_meta" in plan_output
        assert "task_ids" in plan_output["plan_meta"]
        assert "executor_agent" in plan_output["plan_meta"]
        assert len(plan_output["plan_meta"]["task_ids"]) > 0, "Should have at least one task"
        
        print(f"\n✅ Plan created with {len(plan_output['plan_meta']['task_ids'])} tasks")
        print(f"   Task IDs: {plan_output['plan_meta']['task_ids']}")
        print(f"   Executor: {plan_output['plan_meta']['executor_agent']}")

    print(f"\n✅ Test completed successfully!")
