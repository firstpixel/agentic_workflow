#!/usr/bin/env python3
"""
Test the planner coder flow integration without requiring Ollama connection
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path


from src.app.flow_planner_coder import build_planner_coder_flow
from src.core.workflow_manager import WorkflowManager
from src.core.types import Message, Result


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for testing"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_build_planner_coder_flow(temp_project_dir):
    """Test that the planner coder flow builds correctly"""
    graph, agents, node_policies = build_planner_coder_flow(
        executor_agent_name="TestCodeExecutor",
        project_root=temp_project_dir
    )
    
    # Check graph structure
    assert "Planner" in graph
    assert "Updater" in graph
    assert "TestCodeExecutor" in graph
    
    # Check connections
    assert "Updater" in graph["Planner"]
    assert "TestCodeExecutor" in graph["Updater"]
    assert "Updater" in graph["TestCodeExecutor"]
    
    # Check agents
    assert "Planner" in agents
    assert "Updater" in agents
    assert "TestCodeExecutor" in agents
    
    # Check agent types
    from src.agents.planner_agent import PlannerAgent
    from src.agents.code_executor_agent import CodeExecutorAgent
    from src.app.flows_planner import UpdaterAgent
    
    assert isinstance(agents["Planner"], PlannerAgent)
    assert isinstance(agents["Updater"], UpdaterAgent)
    assert isinstance(agents["TestCodeExecutor"], CodeExecutorAgent)


def test_workflow_manager_integration(temp_project_dir):
    """Test that WorkflowManager can use the planner coder flow"""
    graph, agents, node_policies = build_planner_coder_flow(
        project_root=temp_project_dir
    )
    
    # Create workflow manager
    wm = WorkflowManager(graph=graph, agents=agents, node_policies=node_policies)
    
    # Check that it initializes correctly
    assert wm.graph == graph
    assert wm.agents == agents
    assert wm.node_policies == node_policies


@patch('src.agents.planner_agent.PlannerAgent.run')
@patch('src.agents.code_executor_agent.CodeExecutorAgent._generate_execution_plan')
def test_end_to_end_flow_simulation(mock_generate_plan, mock_planner_run, temp_project_dir):
    """Test end-to-end flow with mocked components"""
    
    # Mock planner output
    mock_planner_run.return_value = Result.ok(
        output={
            "summary_md": "Create a simple calculator",
            "final_plan_md": "Task breakdown for calculator",
            "tasks_md": ["# Task T1 — Create Calculator\nImplement basic arithmetic functions"],
            "plan_meta": {
                "executor_agent": "CodeExecutor",
                "task_ids": ["T1"],
                "dag_edges": [],
                "version": "v1"
            }
        },
        display_output="Planner completed successfully",
        control={"goto": "Updater"}
    )
    
    # Mock code executor LLM response
    mock_generate_plan.return_value = {
        "files": [
            {
                "path": "calc.py",
                "content": "def add(a, b): return a + b",
                "language": "python"
            }
        ],
        "scripts": [],
        "tests": [
            {
                "type": "python",
                "file": "calc.py",
                "description": "Test calculator syntax"
            }
        ]
    }
    
    # Build flow
    graph, agents, node_policies = build_planner_coder_flow(
        project_root=temp_project_dir
    )
    
    # Create workflow manager
    wm = WorkflowManager(graph=graph, agents=agents, node_policies=node_policies)
    
    # Run workflow
    results = wm.run_workflow("Planner", {"text": "Create a calculator"})
    
    # Check results
    assert len(results) >= 1  # At least planner result
    
    # Find the planner result
    planner_result = None
    for result in results:
        if result.success and result.output and "plan_meta" in result.output:
            planner_result = result
            break
    
    assert planner_result is not None
    assert planner_result.success
    assert "task_ids" in planner_result.output["plan_meta"]


def test_configuration_options():
    """Test different configuration options for the flow"""
    
    # Test with custom executor name
    graph, agents, node_policies = build_planner_coder_flow(
        executor_agent_name="MyExecutor",
        project_root="./test_output"
    )
    
    assert "MyExecutor" in agents
    assert "MyExecutor" in graph
    
    # Test with custom model config
    executor_config = {
        "enable_execution": False,
        "allowed_extensions": [".py", ".txt"]
    }
    
    graph, agents, node_policies = build_planner_coder_flow(
        executor_model_config=executor_config
    )
    
    executor = agents["CodeExecutor"]
    assert executor.enable_execution is False
    assert executor.allowed_extensions == [".py", ".txt"]


def test_flow_builder_parameters():
    """Test that all flow builder parameters work correctly"""
    graph, agents, node_policies = build_planner_coder_flow(
        executor_agent_name="CustomExecutor",
        executor_model_config={
            "project_root": "/tmp/test",
            "enable_execution": False
        },
        retry_limit=5,
        planner_model_config={
            "executor_agent": "CustomExecutor",
            "model": "test-model"
        },
        project_root="/tmp/custom"
    )
    
    # Check executor configuration
    executor = agents["CustomExecutor"]
    assert str(executor.project_root) == "/tmp/custom"  # project_root parameter overrides model_config
    assert executor.enable_execution is False
    
    # Check updater retry limit
    updater = agents["Updater"]
    assert updater.config.model_config["retry_limit"] == 5
    
    # Check planner model config
    planner = agents["Planner"]
    assert planner.config.model_config["executor_agent"] == "CustomExecutor"
    assert planner.config.model_config["model"] == "test-model"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])