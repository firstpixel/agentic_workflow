#!/usr/bin/env python3

import os
from src.app.flows_planner import build_planner_flow
from src.core.workflow_manager import WorkflowManager

# Build flow
graph, agents, node_policies = build_planner_flow(
    executor_agent_name="Executor",
    executor_model_config={"fail_once": True},  
    retry_limit=2,
    planner_model_config={
        "executor_agent": "Executor", 
        "model": os.getenv("OLLAMA_MODEL", "gemma3:latest"),
        "options": {"temperature": 0.1}
    }
)

print("=== FLOW DEBUG ===")
print(f"Graph: {graph}")
print(f"Agents: {list(agents.keys())}")
print(f"Node policies: {node_policies}")

# Test just the Planner first
print("\n=== TESTING PLANNER ALONE ===")
from src.core.types import Message

planner = agents["Planner"]
planner_msg = Message(data={"request": "Build a simple React app"})
planner_result = planner.run(planner_msg)

print(f"Planner result success: {planner_result.success}")
print(f"Planner result control: {planner_result.control}")
print(f"Planner output keys: {list(planner_result.output.keys()) if isinstance(planner_result.output, dict) else 'not dict'}")

if isinstance(planner_result.output, dict) and "plan_meta" in planner_result.output:
    print("✅ Planner output has plan_meta - should work with Updater")
    
    # Test Updater manually
    print("\n=== TESTING UPDATER WITH PLANNER OUTPUT ===")
    updater = agents["Updater"]
    updater_msg = Message(data=planner_result.output)
    updater_result = updater.run(updater_msg)
    
    print(f"Updater result success: {updater_result.success}")
    print(f"Updater result control: {updater_result.control}")
    print(f"Updater output keys: {list(updater_result.output.keys()) if isinstance(updater_result.output, dict) else 'not dict'}")
else:
    print("❌ Planner output missing plan_meta")

# Now test the full workflow
print("\n=== TESTING FULL WORKFLOW ===")
wm = WorkflowManager(graph=graph, agents=agents, node_policies=node_policies)

results = wm.run_workflow("Planner", {"request": "Build a simple React app"})

print(f"\nWorkflow results count: {len(results)}")
for i, result in enumerate(results):
    print(f"Result {i+1}: success={result.success}, display='{result.display_output}'")
    if hasattr(result, 'metrics') and 'agent' in result.metrics:
        print(f"  Agent: {result.metrics['agent']}")