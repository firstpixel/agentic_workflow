#!/usr/bin/env python3
"""
Test CodeExecutorAgent functionality without requiring Ollama connection
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.agents.code_executor_agent import CodeExecutorAgent
from src.core.agent import AgentConfig
from src.core.types import Message, Result


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for testing"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def code_executor_agent(temp_project_dir):
    """Create a CodeExecutorAgent for testing"""
    config = AgentConfig(
        name="TestCodeExecutor",
        prompt_file="code_executor.md",
        model_config={
            "project_root": temp_project_dir,
            "enable_execution": True,
            "allowed_extensions": [".py", ".js", ".html", ".txt", ".md"]
        }
    )
    return CodeExecutorAgent(config)


def test_code_executor_agent_initialization(code_executor_agent, temp_project_dir):
    """Test that CodeExecutorAgent initializes correctly"""
    assert code_executor_agent.project_root == Path(temp_project_dir).resolve()
    assert code_executor_agent.enable_execution is True
    assert ".py" in code_executor_agent.allowed_extensions
    assert code_executor_agent.project_root.exists()


def test_find_task_in_plan(code_executor_agent):
    """Test finding task details in plan state"""
    plan_state = {
        "tasks_md": [
            "# Task T1 — Setup Python Environment\nCreate basic Python project structure",
            "# Task T2 — Create Calculator\nImplement calculator functions"
        ]
    }
    
    task_details = code_executor_agent._find_task_in_plan("T1", plan_state)
    assert task_details is not None
    assert task_details["id"] == "T1"
    assert "Setup Python Environment" in task_details["title"]
    
    # Test non-existent task
    task_details = code_executor_agent._find_task_in_plan("T999", plan_state)
    assert task_details is None


def test_parse_execution_plan_markdown(code_executor_agent):
    """Test parsing execution plan from markdown response"""
    markdown_response = '''
    Here's the execution plan:
    
    ```bash
    # Create project structure
    mkdir -p src
    
    # Create calculator file
    cat > calculator.py << 'EOF'
    def add(a, b): 
        return a + b
    
    def subtract(a, b):
        return a - b
    EOF
    
    # Validate Python syntax
    python -m py_compile calculator.py
    
    echo 'Calculator project setup complete'
    ```
    '''
    
    plan = code_executor_agent._parse_execution_plan(markdown_response)
    assert plan is not None
    assert len(plan["files"]) == 1
    assert len(plan["scripts"]) == 1
    assert plan["files"][0]["path"] == "calculator.py"
    assert "def add" in plan["files"][0]["content"]


def test_parse_execution_plan_fallback(code_executor_agent):
    """Test fallback parsing when only bash blocks are found"""
    response = '''
    Here's some bash script:
    
    ```bash
    # Create project structure
    mkdir -p src
    
    cat > src/hello.py << 'EOF'
    def hello():
        print("Hello, World!")
    EOF
    
    echo "Setting up project"
    ```
    '''
    
    plan = code_executor_agent._parse_execution_plan(response)
    assert plan is not None
    assert len(plan["files"]) == 1  # File extracted from bash script
    assert len(plan["scripts"]) == 1  # Bash script
    assert plan["files"][0]["path"] == "src/hello.py"


def test_create_file(code_executor_agent, temp_project_dir):
    """Test file creation functionality"""
    task_dir = Path(temp_project_dir) / "test_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    
    file_spec = {
        "path": "hello.py",
        "content": "print('Hello, World!')",
        "language": "python"
    }
    
    result = code_executor_agent._create_file(file_spec, task_dir)
    
    assert result["success"] is True
    assert "hello.py" in result["message"]
    
    # Check file was actually created
    created_file = task_dir / "hello.py"
    assert created_file.exists()
    assert created_file.read_text() == "print('Hello, World!')"


def test_create_file_security_check(code_executor_agent, temp_project_dir):
    """Test that file creation prevents path traversal attacks"""
    task_dir = Path(temp_project_dir) / "test_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    
    # Try to create file outside task directory
    file_spec = {
        "path": "../../../etc/passwd",
        "content": "malicious content",
        "language": "text"
    }
    
    result = code_executor_agent._create_file(file_spec, task_dir)
    
    assert result["success"] is False
    assert "outside allowed directory" in result["message"]


def test_create_file_extension_check(code_executor_agent, temp_project_dir):
    """Test that file creation only allows permitted extensions"""
    task_dir = Path(temp_project_dir) / "test_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    
    # Try to create file with disallowed extension
    file_spec = {
        "path": "malware.exe",
        "content": "binary content",
        "language": "binary"
    }
    
    result = code_executor_agent._create_file(file_spec, task_dir)
    
    assert result["success"] is False
    assert "not allowed" in result["message"]


def test_execute_script_disabled(temp_project_dir):
    """Test script execution when disabled"""
    config = AgentConfig(
        name="TestCodeExecutor",
        prompt_file="code_executor.md",
        model_config={
            "project_root": temp_project_dir,
            "enable_execution": False  # Disabled
        }
    )
    agent = CodeExecutorAgent(config)
    
    task_dir = Path(temp_project_dir) / "test_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    
    script = {
        "code": "echo 'Hello'",
        "description": "Test script"
    }
    
    result = agent._execute_script(script, task_dir)
    
    assert result["success"] is True
    assert "dry-run mode" in result["message"]


def test_execute_script_empty_code(code_executor_agent, temp_project_dir):
    """Test script execution with empty code"""
    task_dir = Path(temp_project_dir) / "test_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    
    script = {
        "code": "",
        "description": "Empty script"
    }
    
    result = code_executor_agent._execute_script(script, task_dir)
    
    assert result["success"] is False
    assert "Empty script code" in result["message"]


def test_run_with_missing_task_id(code_executor_agent):
    """Test main run method with missing task_id"""
    message = Message(data={
        "executor_payload": {
            # Missing task_id
            "plan_state": {}
        }
    })
    
    result = code_executor_agent.run(message)
    
    assert result.success is False
    assert "No task_id provided" in result.output["error"]


def test_run_with_task_not_found(code_executor_agent):
    """Test main run method when task is not found in plan"""
    message = Message(data={
        "executor_payload": {
            "task_id": "NONEXISTENT",
            "plan_state": {
                "tasks_md": ["# Task T1 — Some other task"]
            }
        }
    })
    
    result = code_executor_agent.run(message)
    
    assert result.success is False
    assert "not found in plan" in result.output["error"]


@patch('src.agents.code_executor_agent.CodeExecutorAgent._generate_execution_plan')
def test_run_success_flow(mock_generate_plan, code_executor_agent, temp_project_dir):
    """Test successful execution flow"""
    # Mock the LLM call to return a simple plan
    mock_generate_plan.return_value = {
        "files": [
            {
                "path": "test.py",
                "content": "print('Hello from test')",
                "language": "python"
            }
        ],
        "scripts": [],
        "tests": []
    }
    
    message = Message(data={
        "executor_payload": {
            "task_id": "T1",
            "plan_state": {
                "tasks_md": ["# Task T1 — Create Test File\nCreate a simple test file"]
            }
        }
    })
    
    result = code_executor_agent.run(message)
    
    assert result.success is True
    assert "SUCCESS" in result.display_output
    assert result.output["task_id"] == "T1"
    assert len(result.output["execution_results"]) == 1
    
    # Check that file was created
    task_dir = Path(temp_project_dir) / "T1" / "test.py"
    assert task_dir.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])