"""
Task Manager for CAI Web Backend
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
import traceback
import json

from .models import Task, TaskStatus
from ...sdk.agents import Agent
from ...sdk.agents.run import Runner
from .websocket_manager import websocket_manager


class TaskManager:
    """Manages CAI agent tasks with parallel execution support"""
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._background_tasks: List[asyncio.Task] = []
    
    async def create_task(
        self,
        session_id: str,
        message: str,
        agent: Agent
    ) -> Task:
        """Create and start a new task"""
        async with self._lock:
            # Create task
            task = Task(
                session_id=session_id,
                message=message
            )
            self.tasks[task.id] = task
            
            # Start task execution
            asyncio_task = asyncio.create_task(
                self._execute_task(task, agent)
            )
            self.running_tasks[task.id] = asyncio_task
            
            return task
    
    async def _execute_task(self, task: Task, agent: Agent):
        """Execute a task with the given agent - simplified like CLI"""
        try:
            # Update task status
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            await self._notify_task_update(task)
            
            # Run the agent like CLI does - simple and clean
            result = await Runner.run(
                starting_agent=agent,
                input=task.message
            )
            
            # Extract messages and tools used from result (like CLI)
            initial_message = ""  # First thinking message 
            final_message = ""    # Final response after tools
            tools_used = []
            tool_commands = {}    # Store tool commands for thinking display
            tool_outputs = {}     # Store tool outputs for detailed task view
            
            # Process new_items to extract response and tool usage
            if hasattr(result, 'new_items') and result.new_items:
                for idx, item in enumerate(result.new_items):
                    # Extract tool usage from ToolCallItem or ToolCallOutputItem
                    if hasattr(item, 'type'):
                        item_type_str = str(item.type).lower()
                        
                        # Check for tool call items
                        if 'tool_call' in item_type_str:
                            tool_name = None
                            tool_args = None
                            
                            # Try multiple ways to extract tool name and args
                            if hasattr(item, 'tool_name') and item.tool_name:
                                tool_name = item.tool_name
                            elif hasattr(item, 'raw_item') and hasattr(item.raw_item, 'tool_calls'):
                                # Extract from raw OpenAI tool call
                                tool_calls = item.raw_item.tool_calls
                                if tool_calls and len(tool_calls) > 0:
                                    tool_name = tool_calls[0].function.name
                                    try:
                                        import json
                                        tool_args = json.loads(tool_calls[0].function.arguments)
                                    except:
                                        tool_args = tool_calls[0].function.arguments
                            elif hasattr(item, 'raw_item') and hasattr(item.raw_item, 'name'):
                                tool_name = item.raw_item.name
                            
                            if tool_name:
                                tools_used.append(tool_name)
                                # Store command for thinking display
                                if tool_args:
                                    if tool_name == 'generic_linux_command' and 'command' in tool_args:
                                        tool_commands[tool_name] = f"Executing Command: {tool_args['command']}"
                                    else:
                                        tool_commands[tool_name] = f"Executing {tool_name}: {str(tool_args)[:100]}"
                                else:
                                    tool_commands[tool_name] = f"Executing {tool_name}"
                        
                        # Extract assistant messages from MessageOutputItem  
                        elif 'message_output' in item_type_str or 'message' in item_type_str:
                            if hasattr(item, 'raw_item') and hasattr(item.raw_item, 'content'):
                                # Extract text from content array
                                content_items = item.raw_item.content
                                if content_items and len(content_items) > 0:
                                    content_item = content_items[0]
                                    message_text = ""
                                    if hasattr(content_item, 'text'):
                                        message_text = content_item.text
                                    elif hasattr(content_item, 'content'):
                                        message_text = content_item.content
                                    else:
                                        message_text = str(content_item)
                                    
                                    # First message = initial thinking, last message = final response
                                    if not initial_message and message_text:
                                        initial_message = message_text
                                    elif message_text and message_text != initial_message:
                                        final_message = message_text
                        
                        # Extract tool output for detailed task view
                        elif 'tool_call_output' in item_type_str:
                            if hasattr(item, 'output'):
                                # Store output for the task details
                                tool_outputs[len(tool_outputs)] = str(item.output)[:2000]  # Limit size
            
            # Remove duplicates from tools_used  
            tools_used = list(set(tools_used))
            
            # For task result, prioritize tool outputs over AI messages
            task_result = ""
            
            # Use tool outputs as primary task result 
            if tool_outputs:
                # Combine all tool outputs
                tool_output_texts = []
                for output in tool_outputs.values():
                    tool_output_texts.append(str(output))
                task_result = "\n\n".join(tool_output_texts)
            elif tools_used:
                task_result = f"Executed tools: {', '.join(tools_used)}"
            else:
                # Fallback to AI response if no tools were used
                assistant_message = final_message if final_message else initial_message
                if assistant_message:
                    task_result = assistant_message
                else:
                    task_result = "Task completed"
            
            # Set task result 
            task.result = task_result
                
            # Store additional metadata for task details
            task.metadata = {
                "initial_thinking": initial_message if initial_message else None,
                "final_response": final_message if final_message else None,
                "tool_commands": tool_commands,
                "tool_outputs": tool_outputs
            }
            
            # Update task status
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.tools_used = tools_used
            
            # Simple logs for tools used
            task.logs = [
                {
                    "type": "tool_executed",
                    "tool": tool_name,
                    "timestamp": datetime.utcnow().isoformat()
                }
                for tool_name in tools_used
            ]
            
            # Get token usage if available
            if hasattr(result, 'raw_responses') and result.raw_responses:
                total_prompt_tokens = 0
                total_completion_tokens = 0
                total_tokens = 0
                
                for response in result.raw_responses:
                    if hasattr(response, 'usage') and response.usage:
                        total_prompt_tokens += getattr(response.usage, 'prompt_tokens', 0)
                        total_completion_tokens += getattr(response.usage, 'completion_tokens', 0)
                        total_tokens += getattr(response.usage, 'total_tokens', 0)
                
                if total_tokens > 0:
                    task.token_usage = {
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": total_tokens
                    }
            
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.error = "Task was cancelled"
            raise
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.logs.append({
                "type": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat()
            })
        finally:
            # Clean up
            task.completed_at = datetime.utcnow()
            if task.id in self.running_tasks:
                del self.running_tasks[task.id]
            
            # Notify completion
            await self._notify_task_update(task)
    
    async def _notify_task_update(self, task: Task):
        """Notify WebSocket clients of task update"""
        await websocket_manager.broadcast_to_session(
            task.session_id,
            {
                "type": "task_update",
                "task": task.to_dict()
            }
        )
    
    async def _notify_task_log(self, task: Task, log_entry: Dict[str, Any]):
        """Notify WebSocket clients of new log entry"""
        await websocket_manager.broadcast_to_session(
            task.session_id,
            {
                "type": "task_log",
                "task_id": task.id,
                "log": log_entry
            }
        )
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        return self.tasks.get(task_id)
    
    async def wait_for_task(self, task_id: str, timeout: float = 60.0) -> bool:
        """Wait for a task to complete"""
        if task_id not in self.running_tasks:
            return True  # Task already completed or doesn't exist
        
        try:
            await asyncio.wait_for(self.running_tasks[task_id], timeout=timeout)
            return True
        except asyncio.TimeoutError:
            # Cancel the task if it times out
            if task_id in self.running_tasks:
                self.running_tasks[task_id].cancel()
            
            # Update task status
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.status = TaskStatus.FAILED
                task.error = f"Task timed out after {timeout} seconds"
                task.completed_at = datetime.utcnow()
            
            return False
        except Exception as e:
            return False
    
    def get_session_tasks(self, session_id: str) -> List[Task]:
        """Get all tasks for a session"""
        return [
            task for task in self.tasks.values()
            if task.session_id == session_id
        ]
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        async with self._lock:
            if task_id in self.running_tasks:
                self.running_tasks[task_id].cancel()
                return True
            return False
    
    def start_background_tasks(self):
        """Start background tasks for cleanup, etc."""
        # Add any background tasks here (e.g., cleanup old tasks)
        pass
    
    async def cleanup(self):
        """Clean up all running tasks"""
        # Cancel all running tasks
        for task in self.running_tasks.values():
            task.cancel()
        
        # Wait for all tasks to complete
        if self.running_tasks:
            await asyncio.gather(
                *self.running_tasks.values(),
                return_exceptions=True
            )
        
        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
        
        if self._background_tasks:
            await asyncio.gather(
                *self._background_tasks,
                return_exceptions=True
            )
