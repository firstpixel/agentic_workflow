"""
Tests for demo_code_executor.py script functionality

Tests both mocked and real LLM modes to ensure dual-mode operation works correctly.
"""
import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, Mock

# Add src to Python path for imports
test_dir = Path(__file__).parent
project_root = test_dir.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Import demo functions
from demo_code_executor import (
    create_demo_agent, 
    demo_task_execution, 
    mock_llm_response_python_calculator,
    parse_arguments,
    should_use_real_llm
)
from tests.test_utils import skip_if_no_ollama, setup_test_environment


class TestDemoCodeExecutor:
    """Test suite for demo_code_executor functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment"""
        self.original_dir = os.getcwd()
        self.temp_dir = tempfile.mkdtemp()
        os.chdir(self.temp_dir)
        setup_test_environment()
        yield
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_demo_agent_mock_mode(self):
        """Test that create_demo_agent works in mock mode"""
        agent = create_demo_agent("test_project", use_real_llm=False)
        assert agent is not None
        assert agent.config.name == "DemoCodeExecutor"
        assert "test_project" in str(agent.project_root)
    
    def test_create_demo_agent_real_llm_mode(self):
        """Test that create_demo_agent works in real LLM mode"""
        agent = create_demo_agent("test_project", use_real_llm=True)
        assert agent is not None
        assert agent.config.name == "DemoCodeExecutor"
        assert "test_project" in str(agent.project_root)
    
    def test_mock_llm_response_python_calculator(self):
        """Test that mock response function returns expected structure"""
        response = mock_llm_response_python_calculator()
        assert isinstance(response, dict)
        assert "files" in response
        assert "scripts" in response
        assert "tests" in response
        
        # Check file structure
        files = response["files"]
        assert len(files) >= 2  # At least calculator.py and README.md
        
        # Verify first file has required fields
        first_file = files[0]
        assert "path" in first_file
        assert "content" in first_file
        assert "description" in first_file
    
    def test_parse_arguments_default(self):
        """Test argument parsing with no arguments (default mode)"""
        with patch('sys.argv', ['demo_code_executor.py']):
            args = parse_arguments()
            assert not args.use_real_llm
    
    def test_parse_arguments_use_real_llm(self):
        """Test argument parsing with --use-real-llm flag"""
        with patch('sys.argv', ['demo_code_executor.py', '--use-real-llm']):
            args = parse_arguments()
            assert args.use_real_llm
    
    def test_should_use_real_llm_cli_flag(self):
        """Test should_use_real_llm with CLI flag"""
        mock_args = Mock()
        mock_args.use_real_llm = True
        
        assert should_use_real_llm(mock_args) is True
    
    def test_should_use_real_llm_env_var(self):
        """Test should_use_real_llm with environment variable"""
        mock_args = Mock()
        mock_args.use_real_llm = False
        
        # Test various env var values
        test_cases = [
            ("1", True),
            ("true", True), 
            ("yes", True),
            ("on", True),
            ("TRUE", True),  # case insensitive
            ("0", False),
            ("false", False),
            ("", False),
        ]
        
        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"USE_REAL_LLM": env_value}):
                result = should_use_real_llm(mock_args)
                assert result == expected, f"Failed for env value: {env_value}"
    
    def test_should_use_real_llm_cli_overrides_env(self):
        """Test that CLI flag overrides environment variable"""
        mock_args = Mock()
        mock_args.use_real_llm = True
        
        # Even with env var set to false, CLI flag should win
        with patch.dict(os.environ, {"USE_REAL_LLM": "false"}):
            assert should_use_real_llm(mock_args) is True
    
    @patch('demo_code_executor.Path.exists', return_value=True)
    @patch('demo_code_executor.Path.rglob')
    @patch('demo_code_executor.Path.stat')
    def test_demo_task_execution_mock_mode(self, mock_stat, mock_rglob, mock_exists):
        """Test demo_task_execution in mock mode"""
        # Setup mocks
        mock_file = Mock()
        mock_file.is_file.return_value = True
        mock_file.relative_to.return_value = Path("test_file.py")
        mock_rglob.return_value = [mock_file]
        
        mock_stat_result = Mock()
        mock_stat_result.st_size = 100
        mock_stat.return_value = mock_stat_result
        
        # Mock successful agent execution
        with patch('demo_code_executor.create_demo_agent') as mock_create_agent:
            mock_agent = Mock()
            mock_agent.project_root = Path("/tmp/test")
            mock_result = Mock()
            mock_result.success = True
            mock_result.display_output = "Test completed"
            mock_result.output = {"execution_results": []}
            mock_agent.run.return_value = mock_result
            mock_create_agent.return_value = mock_agent
            
            # This should not raise any exceptions
            try:
                demo_task_execution(
                    "Test Project",
                    "Test Task", 
                    mock_llm_response_python_calculator,
                    use_real_llm=False
                )
            except Exception as e:
                pytest.fail(f"demo_task_execution failed in mock mode: {e}")
    
    @skip_if_no_ollama()
    def test_demo_task_execution_real_llm_mode(self):
        """Test demo_task_execution in real LLM mode (requires Ollama)"""
        # This test will be skipped if Ollama is not available
        try:
            demo_task_execution(
                "Test Project",
                "Create a simple Python hello world script",
                mock_llm_response_python_calculator,  # Won't be used in real mode
                use_real_llm=True
            )
        except Exception as e:
            # Real LLM might fail due to network/model issues, but shouldn't crash
            # We mainly want to ensure the code path doesn't have syntax errors
            if "ollama" in str(e).lower():
                pytest.skip(f"Ollama service issue: {e}")
            else:
                pytest.fail(f"Unexpected error in real LLM mode: {e}")


if __name__ == "__main__":
    pytest.main([__file__])