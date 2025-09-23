"""
Updater Agent: Manages task execution progress and handles failures.

Flow:
User → Planner → Updater ← Executor
                     ↓
              (on failure after retries)
                 Planner (Refiner)
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import time
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class TaskExecution:
    task_id: str
    status: TaskStatus
    attempt_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    execution_log: List[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def __post_init__(self):
        if self.execution_log is None:
            self.execution_log = []

class UpdaterAgent:
    """
    Manages task execution state and coordinates with Executor and Planner.
    
    Responsibilities:
    1. Track task completion status with checkmarks
    2. Handle task failures and retries
    3. Trigger task refinement when max retries exceeded
    4. Coordinate between Executor and Planner
    """
    
    def __init__(self, workflow_manager, max_retries: int = 3):
        self.workflow_manager = workflow_manager
        self.max_retries = max_retries
        self.task_executions: Dict[str, TaskExecution] = {}
        self.task_plan: Dict[str, Any] = {}
        
    def initialize_task_plan(self, tasks: List[Dict[str, Any]]):
        """Initialize tracking for all tasks in the plan."""
        self.task_plan = {task['id']: task for task in tasks}
        
        for task in tasks:
            task_id = task['id']
            self.task_executions[task_id] = TaskExecution(
                task_id=task_id,
                status=TaskStatus.PENDING,
                max_retries=self.max_retries
            )
        
        print(f"📋 Initialized task plan with {len(tasks)} tasks")
        self._display_task_status()
    
    def start_task_execution(self, task_id: str) -> bool:
        """Mark task as in progress."""
        if task_id not in self.task_executions:
            print(f"❌ Task {task_id} not found in plan")
            return False
            
        execution = self.task_executions[task_id]
        execution.status = TaskStatus.IN_PROGRESS
        execution.start_time = time.time()
        execution.attempt_count += 1
        
        print(f"🚀 Starting execution of {task_id} (attempt {execution.attempt_count})")
        return True
    
    def mark_task_completed(self, task_id: str, execution_result: Optional[Dict] = None):
        """Mark task as completed with green checkmark."""
        if task_id not in self.task_executions:
            print(f"❌ Task {task_id} not found in plan")
            return
            
        execution = self.task_executions[task_id]
        execution.status = TaskStatus.COMPLETED
        execution.end_time = time.time()
        execution.execution_log.append(f"✅ Task completed successfully")
        
        if execution_result:
            execution.execution_log.append(f"Result: {execution_result}")
        
        print(f"✅ Task {task_id} completed successfully!")
        self._display_task_status()
        
        # Check if all tasks are complete
        if self._all_tasks_completed():
            print("🎉 All tasks completed! Project finished successfully.")
    
    def handle_task_failure(self, task_id: str, error: str) -> str:
        """
        Handle task failure with retry logic or refinement trigger.
        
        Returns:
        - "retry": Executor should retry the task
        - "refine": Planner should refine the task
        - "abort": Fatal error, stop execution
        """
        if task_id not in self.task_executions:
            print(f"❌ Task {task_id} not found in plan")
            return "abort"
            
        execution = self.task_executions[task_id]
        execution.error_message = error
        execution.execution_log.append(f"❌ Attempt {execution.attempt_count} failed: {error}")
        
        print(f"❌ Task {task_id} failed (attempt {execution.attempt_count}): {error}")
        
        # Check if we should retry
        if execution.attempt_count < execution.max_retries:
            execution.status = TaskStatus.RETRYING
            print(f"🔄 Retrying {task_id} (attempt {execution.attempt_count + 1}/{execution.max_retries})")
            return "retry"
        else:
            # Max retries exceeded - trigger refinement
            execution.status = TaskStatus.FAILED
            print(f"💥 Task {task_id} failed after {execution.max_retries} attempts")
            print(f"🔧 Triggering task refinement via Planner...")
            return "refine"
    
    def get_next_executable_task(self) -> Optional[str]:
        """Get the next task that can be executed based on dependencies."""
        for task_id, task in self.task_plan.items():
            execution = self.task_executions[task_id]
            
            # Skip if already completed or in progress
            if execution.status in [TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS]:
                continue
                
            # Check if all dependencies are completed
            dependencies = task.get('dependencies', [])
            if dependencies == ['None'] or dependencies == []:
                dependencies = []
                
            deps_completed = all(
                self.task_executions[dep_id].status == TaskStatus.COMPLETED 
                for dep_id in dependencies
                if dep_id in self.task_executions
            )
            
            if deps_completed:
                return task_id
                
        return None
    
    def _all_tasks_completed(self) -> bool:
        """Check if all tasks are completed."""
        return all(
            execution.status == TaskStatus.COMPLETED 
            for execution in self.task_executions.values()
        )
    
    def _display_task_status(self):
        """Display current status of all tasks with visual indicators."""
        print("\n📊 TASK STATUS DASHBOARD")
        print("=" * 50)
        
        for task_id in sorted(self.task_plan.keys()):
            execution = self.task_executions[task_id]
            task = self.task_plan[task_id]
            
            # Status emoji
            status_emoji = {
                TaskStatus.PENDING: "⏳",
                TaskStatus.IN_PROGRESS: "🔄", 
                TaskStatus.COMPLETED: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.RETRYING: "🔄"
            }
            
            emoji = status_emoji.get(execution.status, "❓")
            task_name = task.get('name', task_id)
            
            # Retry indicator
            retry_info = ""
            if execution.attempt_count > 1:
                retry_info = f" (attempt {execution.attempt_count})"
            
            print(f"{emoji} {task_id}: {task_name}{retry_info}")
            
            # Show error for failed tasks
            if execution.status == TaskStatus.FAILED and execution.error_message:
                print(f"    💥 Error: {execution.error_message}")
        
        print("=" * 50)
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of execution progress."""
        total_tasks = len(self.task_executions)
        completed = sum(1 for e in self.task_executions.values() if e.status == TaskStatus.COMPLETED)
        failed = sum(1 for e in self.task_executions.values() if e.status == TaskStatus.FAILED)
        in_progress = sum(1 for e in self.task_executions.values() if e.status == TaskStatus.IN_PROGRESS)
        
        return {
            "total_tasks": total_tasks,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "completion_rate": completed / total_tasks if total_tasks > 0 else 0,
            "tasks": {
                task_id: {
                    "status": execution.status.value,
                    "attempts": execution.attempt_count,
                    "error": execution.error_message
                }
                for task_id, execution in self.task_executions.items()
            }
        }
    
    async def execute_workflow(self):
        """Main execution loop coordinating with Executor and Planner."""
        print("🎯 Starting workflow execution...")
        
        while True:
            next_task = self.get_next_executable_task()
            
            if next_task is None:
                if self._all_tasks_completed():
                    print("🎉 Workflow completed successfully!")
                    break
                else:
                    # Check if we have failed tasks that need refinement
                    failed_tasks = [
                        task_id for task_id, execution in self.task_executions.items()
                        if execution.status == TaskStatus.FAILED
                    ]
                    
                    if failed_tasks:
                        print(f"💥 Found failed tasks requiring refinement: {failed_tasks}")
                        for task_id in failed_tasks:
                            await self._trigger_task_refinement(task_id)
                    else:
                        print("⚠️  No executable tasks found but workflow not complete")
                        break
            else:
                # Execute the next task
                await self._execute_single_task(next_task)
    
    async def _execute_single_task(self, task_id: str):
        """Execute a single task via the Executor."""
        self.start_task_execution(task_id)
        
        try:
            # Call the Executor agent
            result = await self.workflow_manager.route_message({
                "type": "execute_task",
                "task_id": task_id,
                "task_details": self.task_plan[task_id],
                "source": "updater"
            }, "executor")
            
            if result.get("success", False):
                self.mark_task_completed(task_id, result)
            else:
                error_msg = result.get("error", "Unknown execution error")
                action = self.handle_task_failure(task_id, error_msg)
                
                if action == "retry":
                    # Retry the task
                    await self._execute_single_task(task_id)
                elif action == "refine":
                    await self._trigger_task_refinement(task_id)
                    
        except Exception as e:
            error_msg = f"Executor error: {str(e)}"
            action = self.handle_task_failure(task_id, error_msg)
            
            if action == "retry":
                await self._execute_single_task(task_id)
            elif action == "refine":
                await self._trigger_task_refinement(task_id)
    
    async def _trigger_task_refinement(self, task_id: str):
        """Trigger task refinement via the Planner."""
        print(f"🔧 Triggering refinement for task {task_id}")
        
        execution = self.task_executions[task_id]
        
        try:
            # Call the Planner to refine the failed task
            result = await self.workflow_manager.route_message({
                "type": "refine_task",
                "task_id": task_id,
                "task_details": self.task_plan[task_id],
                "failure_info": {
                    "error": execution.error_message,
                    "attempts": execution.attempt_count,
                    "execution_log": execution.execution_log
                },
                "source": "updater"
            }, "planner")
            
            if result.get("success", False):
                # Update the task plan with refined tasks
                refined_tasks = result.get("refined_tasks", [])
                if refined_tasks:
                    print(f"✨ Task {task_id} refined into {len(refined_tasks)} new tasks")
                    # Update the task plan and tracking
                    # This would involve updating self.task_plan and self.task_executions
                    
        except Exception as e:
            print(f"❌ Failed to refine task {task_id}: {str(e)}")