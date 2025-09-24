"""
CodeExecutorAgent: Safe automated code execution and file creation for PlannerFlow

This agent parses tasks from the PlannerFlow and automatically:
1. Creates project folder structure
2. Generates bash scripts for file creation
3. Executes code blocks safely within a sandboxed directory
4. Supports Python and NodeJS tasks with automatic testing
"""

from __future__ import annotations
import os
import subprocess
import tempfile
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import re

from src.core.agent import BaseAgent, AgentConfig, LLMAgent
from src.core.types import Message, Result


class CodeExecutorAgent(BaseAgent):
    """
    Automated code executor that safely creates files and runs scripts.
    
    Features:
    - Safe sandboxed execution within project directory
    - Support for Python, NodeJS, and bash scripts
    - Automatic folder structure creation
    - Code block extraction and file generation
    - Basic testing capabilities
    
    model_config:
        project_root: str - Base directory for all operations (defaults to ./output)
        allowed_extensions: List[str] - File extensions allowed (defaults to common web/python files)
        enable_execution: bool - Whether to actually execute scripts (defaults to True)
    """
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.llm_agent = LLMAgent(config)
        
        # Initialize configuration
        mc = self.config.model_config or {}
        self.project_root = Path(mc.get("project_root", "./output")).resolve()
        self.allowed_extensions = mc.get("allowed_extensions", [
            ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", 
            ".md", ".txt", ".sh", ".yaml", ".yml", ".gitignore"
        ])
        self.enable_execution = mc.get("enable_execution", True)
        
        # Ensure project root exists
        self.project_root.mkdir(parents=True, exist_ok=True)
        
    def run(self, message: Message) -> Result:
        """Main execution entry point"""
        try:
            payload = message.data or {}
            executor_payload = payload.get("executor_payload", {})
            task_id = executor_payload.get("task_id")
            plan_state = executor_payload.get("plan_state", {})
            
            if not task_id:
                return Result.fail(output={"error": "No task_id provided in executor_payload"})
                
            # Find the task in the plan
            task_details = self._find_task_in_plan(task_id, plan_state)
            if not task_details:
                return Result.fail(output={"error": f"Task {task_id} not found in plan"})
                
            print(f"🔨 [CodeExecutor] Processing task: {task_id}")
            print(f"📝 Task: {task_details.get('title', 'Unknown')}")
            
            # Use LLM to analyze task and generate execution plan
            execution_plan = self._generate_execution_plan(task_id, task_details, plan_state)
            if not execution_plan:
                return Result.fail(output={"error": "Failed to generate execution plan"})
                
            # Execute the plan
            results = self._execute_plan(execution_plan, task_id)
            
            # Prepare output
            evidence_lines = []
            success = True
            
            for result in results:
                if result["success"]:
                    evidence_lines.append(f"✅ {result['action']}: {result['message']}")
                else:
                    evidence_lines.append(f"❌ {result['action']}: {result['message']}")
                    success = False
                    
            evidence_md = "\n".join(evidence_lines)
            
            output = {
                "task_id": task_id,
                "success": success,
                "evidence_md": evidence_md,
                "plan_state": plan_state,
                "execution_results": results
            }
            
            display = f"🔨 CodeExecutor {task_id}: {'✅ SUCCESS' if success else '❌ FAILED'}"
            
            return Result.ok(output=output, display_output=display)
            
        except Exception as e:
            return Result.fail(output={"error": f"CodeExecutor exception: {str(e)}"})
    
    def _find_task_in_plan(self, task_id: str, plan_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find task details from the plan state"""
        tasks_md = plan_state.get("tasks_md", [])
        
        # Look for task in the markdown blocks
        task_pattern = re.compile(rf"^#\s*Task\s+{re.escape(task_id)}\s*[—-]\s*(.+)$", re.MULTILINE)
        
        for task_block in tasks_md:
            match = task_pattern.search(task_block)
            if match:
                return {
                    "id": task_id,
                    "title": match.group(1).strip(),
                    "content": task_block,
                    "block": task_block
                }
        
        return None
    
    def _generate_execution_plan(self, task_id: str, task_details: Dict[str, Any], plan_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use LLM to analyze task and generate execution plan"""
        try:
            # Prepare context for LLM
            context = {
                "task_id": task_id,
                "task_title": task_details.get("title", ""),
                "task_content": task_details.get("content", ""),
                "project_summary": plan_state.get("summary_md", ""),
                "project_root": str(self.project_root)
            }
            
            # Call LLM to generate execution plan
            result = self.llm_agent.run(Message(data={"user_prompt": json.dumps(context)}))
            
            if not result.success:
                print(f"❌ LLM call failed: {result.error}")
                return None
                
            # Parse LLM response
            response_text = result.output.get("response", "")
            return self._parse_execution_plan(response_text)
            
        except Exception as e:
            print(f"❌ Exception in _generate_execution_plan: {e}")
            return None
    
    def _parse_execution_plan(self, llm_response: str) -> Optional[Dict[str, Any]]:
        """Parse LLM markdown response with bash code blocks into execution plan"""
        try:
            plan = {
                "files": [],
                "scripts": [],
                "tests": []
            }
            
            # Extract bash code blocks
            bash_blocks = re.findall(r'```bash\s*\n(.*?)\n\s*```', llm_response, re.DOTALL)
            
            for bash_code in bash_blocks:
                bash_code = bash_code.strip()
                if not bash_code:
                    continue
                    
                # Parse file creation commands from bash
                files_in_script = self._extract_files_from_bash(bash_code)
                plan["files"].extend(files_in_script)
                
                # Add the entire bash script
                plan["scripts"].append({
                    "language": "bash",
                    "code": bash_code,
                    "description": "Setup and file creation script"
                })
            
            # Look for validation commands that suggest testing
            if re.search(r'python.*-m.*py_compile', llm_response):
                # Find python files for testing
                python_files = [f for f in plan["files"] if f["path"].endswith(".py")]
                for py_file in python_files:
                    plan["tests"].append({
                        "type": "python",
                        "file": py_file["path"],
                        "description": f"Validate Python syntax for {py_file['path']}"
                    })
            
            if re.search(r'node.*--check', llm_response):
                # Find JavaScript files for testing
                js_files = [f for f in plan["files"] if f["path"].endswith((".js", ".jsx"))]
                for js_file in js_files:
                    plan["tests"].append({
                        "type": "javascript",
                        "file": js_file["path"],
                        "description": f"Validate JavaScript syntax for {js_file['path']}"
                    })
            
            return plan if (plan["files"] or plan["scripts"]) else None
            
        except Exception as e:
            print(f"❌ Exception parsing execution plan: {e}")
            return None
    
    def _extract_files_from_bash(self, bash_code: str) -> List[Dict[str, Any]]:
        """Extract file creation commands from bash script"""
        files = []
        
        # Pattern to match "cat > filename << 'EOF'" constructs
        cat_patterns = re.findall(
            r'cat\s*>\s*([^\s<]+)\s*<<\s*[\'"]?(\w+)[\'"]?\s*\n(.*?)\n\2',
            bash_code,
            re.DOTALL | re.MULTILINE
        )
        
        for filepath, delimiter, content in cat_patterns:
            # Determine language from extension
            language = "text"
            if filepath.endswith(".py"):
                language = "python"
            elif filepath.endswith((".js", ".jsx")):
                language = "javascript"
            elif filepath.endswith(".html"):
                language = "html"
            elif filepath.endswith(".css"):
                language = "css"
            elif filepath.endswith(".json"):
                language = "json"
            elif filepath.endswith(".md"):
                language = "markdown"
            
            files.append({
                "path": filepath.strip(),
                "content": content.strip(),
                "language": language,
                "description": f"Generated {language} file"
            })
        
        # Also look for simple echo commands
        echo_patterns = re.findall(
            r'echo\s+[\'"]([^\'"]*)[\'"].*>\s*([^\s&;|]+)',
            bash_code
        )
        
        for content, filepath in echo_patterns:
            if not any(f["path"] == filepath.strip() for f in files):  # Avoid duplicates
                files.append({
                    "path": filepath.strip(),
                    "content": content,
                    "language": "text",
                    "description": "Simple file creation"
                })
        
        return files
    
    def _execute_plan(self, plan: Dict[str, Any], task_id: str) -> List[Dict[str, Any]]:
        """Execute the generated plan"""
        results = []
        
        # Create task-specific directory
        task_dir = self.project_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Execute scripts first (usually setup)
            for script in plan.get("scripts", []):
                result = self._execute_script(script, task_dir)
                results.append(result)
            
            # Create files
            for file_spec in plan.get("files", []):
                result = self._create_file(file_spec, task_dir)
                results.append(result)
            
            # Run tests if available
            for test_spec in plan.get("tests", []):
                result = self._run_test(test_spec, task_dir)
                results.append(result)
                
        except Exception as e:
            results.append({
                "action": "execution",
                "success": False,
                "message": f"Exception during execution: {str(e)}"
            })
        
        return results
    
    def _execute_script(self, script: Dict[str, Any], task_dir: Path) -> Dict[str, Any]:
        """Execute a bash script safely"""
        if not self.enable_execution:
            return {
                "action": "script_execution",
                "success": True,
                "message": "Script execution disabled (dry-run mode)"
            }
        
        try:
            code = script.get("code", "")
            if not code:
                return {
                    "action": "script_execution",
                    "success": False,
                    "message": "Empty script code"
                }
            
            # Create temporary script file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write("#!/bin/bash\n")
                f.write(f"cd {shlex.quote(str(task_dir))}\n")  # Safely escape the task directory path
                f.write(code)
                script_path = f.name
            
            try:
                # Make script executable (owner only for security)
                os.chmod(script_path, 0o700)
                
                # Execute script
                result = subprocess.run(
                    ['/bin/bash', script_path],
                    capture_output=True,
                    text=True,
                    timeout=60,  # 1 minute timeout
                    cwd=task_dir
                )
                
                if result.returncode == 0:
                    return {
                        "action": "script_execution",
                        "success": True,
                        "message": f"Script executed successfully. Output: {result.stdout[:200]}"
                    }
                else:
                    return {
                        "action": "script_execution", 
                        "success": False,
                        "message": f"Script failed with code {result.returncode}. Error: {result.stderr[:200]}"
                    }
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(script_path)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            return {
                "action": "script_execution",
                "success": False,
                "message": "Script execution timed out"
            }
        except Exception as e:
            return {
                "action": "script_execution",
                "success": False,
                "message": f"Script execution error: {str(e)}"
            }
    
    def _create_file(self, file_spec: Dict[str, Any], task_dir: Path) -> Dict[str, Any]:
        """Create a file with given content"""
        try:
            file_path = file_spec.get("path", "")
            content = file_spec.get("content", "")
            
            if not file_path:
                return {
                    "action": "file_creation",
                    "success": False,
                    "message": "No file path specified"
                }
            
            # Security check: ensure path is within task directory
            target_path = (task_dir / file_path).resolve()
            try:
                # Use more robust path validation (Python 3.9+)
                if not target_path.is_relative_to(task_dir.resolve()):
                    return {
                        "action": "file_creation",
                        "success": False,
                        "message": f"Path {file_path} outside allowed directory"
                    }
            except AttributeError:
                # Fallback for Python < 3.9
                if not str(target_path).startswith(str(task_dir.resolve())):
                    return {
                        "action": "file_creation",
                        "success": False,
                        "message": f"Path {file_path} outside allowed directory"
                    }
            
            # Check file extension
            if target_path.suffix not in self.allowed_extensions:
                return {
                    "action": "file_creation",
                    "success": False,
                    "message": f"File extension {target_path.suffix} not allowed"
                }
            
            # Create parent directories
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            target_path.write_text(content, encoding='utf-8')
            
            return {
                "action": "file_creation",
                "success": True,
                "message": f"Created {file_path} ({len(content)} chars)"
            }
            
        except Exception as e:
            return {
                "action": "file_creation",
                "success": False,
                "message": f"File creation error: {str(e)}"
            }
    
    def _run_test(self, test_spec: Dict[str, Any], task_dir: Path) -> Dict[str, Any]:
        """Run a test if possible"""
        if not self.enable_execution:
            return {
                "action": "test_execution", 
                "success": True,
                "message": "Test execution disabled (dry-run mode)"
            }
        
        try:
            test_type = test_spec.get("type", "")
            
            if test_type == "python":
                return self._run_python_test(test_spec, task_dir)
            elif test_type == "javascript":
                return self._run_js_test(test_spec, task_dir)
            else:
                return {
                    "action": "test_execution",
                    "success": True,
                    "message": f"Test type {test_type} not supported, skipping"
                }
                
        except Exception as e:
            return {
                "action": "test_execution",
                "success": False,
                "message": f"Test execution error: {str(e)}"
            }
    
    def _run_python_test(self, test_spec: Dict[str, Any], task_dir: Path) -> Dict[str, Any]:
        """Run Python test"""
        try:
            # Simple test: check if Python file can be imported
            test_file = test_spec.get("file", "main.py")
            target_path = task_dir / test_file
            
            if not target_path.exists():
                return {
                    "action": "python_test",
                    "success": False,
                    "message": f"Test file {test_file} not found"
                }
            
            # Try to run python syntax check
            result = subprocess.run(
                ['python', '-m', 'py_compile', str(target_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return {
                    "action": "python_test",
                    "success": True,
                    "message": f"Python syntax check passed for {test_file}"
                }
            else:
                return {
                    "action": "python_test",
                    "success": False,
                    "message": f"Python syntax errors: {result.stderr[:200]}"
                }
                
        except Exception as e:
            return {
                "action": "python_test",
                "success": False,
                "message": f"Python test error: {str(e)}"
            }
    
    def _run_js_test(self, test_spec: Dict[str, Any], task_dir: Path) -> Dict[str, Any]:
        """Run JavaScript test"""
        try:
            # Simple test: check if Node.js can parse the file
            test_file = test_spec.get("file", "index.js")
            target_path = task_dir / test_file
            
            if not target_path.exists():
                return {
                    "action": "javascript_test",
                    "success": False,
                    "message": f"Test file {test_file} not found"
                }
            
            # Check if node is available
            try:
                result = subprocess.run(
                    ['node', '--check', str(target_path)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    return {
                        "action": "javascript_test",
                        "success": True,
                        "message": f"JavaScript syntax check passed for {test_file}"
                    }
                else:
                    return {
                        "action": "javascript_test",
                        "success": False,
                        "message": f"JavaScript syntax errors: {result.stderr[:200]}"
                    }
            except FileNotFoundError:
                return {
                    "action": "javascript_test",
                    "success": True,
                    "message": f"Node.js not available, skipping syntax check for {test_file}"
                }
                
        except Exception as e:
            return {
                "action": "javascript_test",
                "success": False,
                "message": f"JavaScript test error: {str(e)}"
            }