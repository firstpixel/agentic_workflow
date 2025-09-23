"""
Mock Executor Agent: Simple task execution simulator.

Receives one task per interaction and returns success/failure.
This is a placeholder for the real executor that will be implemented later.
"""

from typing import Dict, Any
import random

from src.core.agent import BaseAgent, AgentConfig
from src.core.types import Message, Result


class ExecutorAgent(BaseAgent):
    """
    Mock Executor that simulates task execution.
    
    For now, this just receives a task and returns success/failure.
    The real executor will be implemented later with actual task execution logic.
    """
    
    def __init__(self, config: AgentConfig, success_rate: float = 0.8):
        super().__init__(config)
        self.success_rate = success_rate  # Configurable success rate for testing
        
    async def process(self, message: Message, **kwargs) -> Result:
        """Process single task execution request from Updater."""
        try:
            data = message.data
            
            if data.get("type") != "execute_task":
                return Result(
                    success=False,
                    error="Executor only handles 'execute_task' messages",
                    data={}
                )
            
            task_id = data.get("task_id")
            task_details = data.get("task_details", {})
            
            print(f"🎯 [MOCK EXECUTOR] Received task {task_id}")
            print(f"📝 Task: {task_details.get('name', 'Unknown task')}")
            
            # Mock execution - simulate success/failure
            success = self._simulate_task_execution(task_id, task_details)
            
            if success:
                return Result(
                    success=True,
                    data={
                        "task_id": task_id,
                        "execution_type": "mock",
                        "output": f"Mock execution of {task_id} completed successfully"
                    },
                    output=f"✅ [MOCK] Task {task_id} completed successfully"
                )
            else:
                return Result(
                    success=False,
                    error=f"Mock execution of task {task_id} failed",
                    data={
                        "task_id": task_id,
                        "execution_type": "mock"
                    }
                )
                
        except Exception as e:
            return Result(
                success=False,
                error=f"Mock Executor exception: {str(e)}",
                data={}
            )
    
    def _simulate_task_execution(self, task_id: str, task_details: Dict[str, Any]) -> bool:
        """
        Simulate task execution with configurable success rate.
        
        Returns:
            bool: True for success, False for failure
        """
        task_name = task_details.get("name", "").lower()
        
        # Some tasks are more likely to succeed than others
        if "setup" in task_name:
            # Setup tasks usually succeed
            success_probability = 0.95
        elif "test" in task_name:
            # Test tasks might fail more often
            success_probability = 0.7
        else:
            # Regular tasks use default success rate
            success_probability = self.success_rate
        
        success = random.random() < success_probability
        
        print(f"🎲 [MOCK] Simulating execution... {'✅ SUCCESS' if success else '❌ FAILURE'}")
        
        return success