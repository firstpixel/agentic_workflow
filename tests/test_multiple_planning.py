#!/usr/bin/env python3
"""
Test multiple planning scenarios with focused logging - shows only LLM responses and key steps
"""

import sys
import os
import pytest
from tests.test_utils import get_test_model_config

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Change to project root directory for relative path resolution
os.chdir(project_root)

from src.agents.planner_agent import PlannerAgent
from src.core.agent import AgentConfig
from src.core.types import Message

# Temporarily suppress detailed debug output
class StepLogger:
    def __init__(self):
        self.current_step = None
        
    def log_step(self, step_name):
        self.current_step = step_name
        print(f"\n🔄 STEP: {step_name}")
        print("-" * 50)

# Override the print function for specific debug messages
original_print = print
step_logger = StepLogger()

def filtered_print(*args, **kwargs):
    """Filter print statements to show only LLM responses and key steps"""
    text = ' '.join(str(arg) for arg in args)
    
    # Show step announcements
    if "Step 1: Decomposing" in text:
        step_logger.log_step("1. DECOMPOSER - Breaking down into tasks")
        return
    elif "Step 2: Summarizing" in text:
        step_logger.log_step("2. SUMMARIZER - Creating overview")
        return
    elif "Step 3: Detailing" in text:
        step_logger.log_step("3. DETAILER - Adding technical details")
        return
    elif "Step 4: Merging" in text:
        step_logger.log_step("4. MERGER - Creating final plan")
        return
    elif "Step 5: Evaluating" in text:
        step_logger.log_step("5. EVALUATOR - Validating plan")
        return
    
    # Show LLM responses
    if "FULL LLM response for" in text:
        stage = text.split("FULL LLM response for")[1].split("(")[0].strip()
        print(f"\n💬 LLM RESPONSE - {stage.upper()}:")
        return
    
    # Show the actual LLM response content (lines of =)
    if text.strip() == "=" * 80:
        return  # Skip the separator, actual content will follow
    
    # Show response content that comes after the separator
    if (step_logger.current_step and 
        "DEBUG" not in text and 
        "🔍" not in text and
        "📋" not in text and
        "🔗" not in text and
        "✅" not in text and
        "❌" not in text and
        len(text.strip()) > 0):
        original_print(text, **kwargs)
        return
    
    # Show final results
    if ("PlannerAgent.run() completed" in text or 
        "tasks=" in text or
        "Success:" in text):
        original_print(*args, **kwargs)

def run_planning_scenario(project_name, request):
    """Helper function to run planning scenario with focused logging"""
    print(f"\n{'='*60}")
    print(f"🧪 TESTING: {project_name}")
    print(f"{'='*60}")
    print(f"📝 Request: {request}")
    
    # Temporarily replace print
    import builtins
    builtins.print = filtered_print
    
    try:
        model_config = get_test_model_config("complex", temperature=0.1)
        model_config["executor_agent"] = "test_executor"
        
        config = AgentConfig(
            name="test_planner",
            model_config=model_config
        )
        
        planner = PlannerAgent(config)
        message = Message(data=request)
        result = planner.run(message)
        
        # Restore original print for results
        builtins.print = original_print
        
        # Show results
        print(f"\n📊 RESULTS:")
        print(f"   Success: {result.success}")
        if result.output and isinstance(result.output, dict):
            plan_meta = result.output.get('plan_meta', {})
            task_ids = plan_meta.get('task_ids', [])
            print(f"   Tasks: {len(task_ids)}")
            if task_ids:
                print(f"   First task: {task_ids[0]}")
        
        return result.success
        
    except Exception as e:
        # Restore original print on error
        builtins.print = original_print
        print(f"❌ ERROR: {e}")
        return False
    finally:
        # Ensure print is restored
        builtins.print = original_print


@pytest.mark.parametrize("project_name,project_request", [
    ("Python Calculator", "Create a python calculator that can add, subtract, multiply and divide numbers."),
    ("React ArXiv App", "Create a react page that uses arxiv rss url to get papers about cs ai, with a search bar, and a filter per day: https://export.arxiv.org/api/query?search_query=all:csai&start=0&max_results=10"),
    ("Sudoku Game", "Create a sudoku game with html and vanilla js."),
])
def test_multiple_planning_scenarios(project_name, project_request):
    """Test planning for different project types"""
    success = run_planning_scenario(project_name, project_request)
    assert success, f"Planning failed for {project_name}"


def test_planner_workflow_integration():
    """Test that detailer processes each task and merger receives all detailed tasks"""
    request = "Create a simple python hello world script with a function and tests."
    
    model_config = get_test_model_config("complex", temperature=0.1)
    model_config["executor_agent"] = "test_executor"
    
    config = AgentConfig(
        name="test_planner",
        model_config=model_config
    )
    
    planner = PlannerAgent(config)
    message = Message(data=request)
    result = planner.run(message)
    
    assert result.success, "Planner workflow should complete successfully"
    assert result.output is not None, "Planner should return output"
    
    if isinstance(result.output, dict):
        plan_meta = result.output.get('plan_meta', {})
        task_ids = plan_meta.get('task_ids', [])
        assert len(task_ids) > 0, "Should generate at least one task"