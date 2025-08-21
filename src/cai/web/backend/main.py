"""
CAI Web Backend - FastAPI application for managing CAI sessions
"""
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from enum import Enum
import json

from cai.web.backend.models import (
    Session, Task, TaskStatus, SessionCreate, SessionResponse,
    TaskResponse, AgentInfo, MessageRequest, ChatMessage
)
from cai.web.backend.session_manager import SessionManager
from cai.web.backend.task_manager import TaskManager
from cai.web.backend.websocket_manager import WebSocketManager


# Initialize managers
session_manager = SessionManager()
task_manager = TaskManager()
websocket_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    task_manager.start_background_tasks()
    yield
    # Shutdown
    await task_manager.cleanup()
    await websocket_manager.disconnect_all()


app = FastAPI(
    title="CAI Web API",
    description="Web API for Cybersecurity AI Framework",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "active_sessions": len(session_manager.sessions),
        "active_tasks": len(task_manager.tasks)
    }


# Session endpoints
@app.post("/sessions", response_model=SessionResponse)
async def create_session(session_data: SessionCreate):
    """Create a new CAI session"""
    try:
        session = await session_manager.create_session(
            agent_type=session_data.agent_type,
            model=session_data.model,
            name=session_data.name,
            config=session_data.config
        )
        return SessionResponse.from_session(session)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/sessions", response_model=List[SessionResponse])
async def list_sessions():
    """List all active sessions"""
    sessions = session_manager.get_all_sessions()
    return [SessionResponse.from_session(s) for s in sessions]


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get a specific session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse.from_session(session)


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    success = await session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted successfully"}


# Message/Chat endpoints
@app.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, message: MessageRequest):
    """Send a message to a session and handle response"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Add user message to session
    user_message = ChatMessage(
        role="user",
        content=message.content,
        tools_used=[]
    )
    session.messages.append(user_message)
    
    # Create and execute task with agent - wait for completion
    task = await task_manager.create_task(
        session_id=session_id,
        message=message.content,
        agent=session.agent
    )
    
    # Wait for task to complete with timeout
    success = await task_manager.wait_for_task(task.id, timeout=120.0)
    
    # Get updated task with results
    completed_task = task_manager.get_task(task.id)
    
    # Determine response content - use AI response for chat, not tool output
    if not success:
        content = "Task timed out after 2 minutes"
    elif completed_task and completed_task.error:
        content = f"Error: {completed_task.error}"
    elif completed_task and completed_task.metadata.get("final_response"):
        # Use AI's final response for chat message
        content = completed_task.metadata["final_response"]
    elif completed_task and completed_task.metadata.get("initial_thinking"):
        # Fallback to initial thinking
        content = completed_task.metadata["initial_thinking"]
    else:
        content = "Agent completed but no response generated"
    
    # Get tools used from completed task
    tools_used_list = completed_task.tools_used if completed_task and completed_task.tools_used else []
    
    # Send tool command thinking message if tools were used
    if completed_task and tools_used_list and completed_task.metadata.get("tool_commands"):
        # Create thinking message from tool commands
        tool_commands = completed_task.metadata["tool_commands"]
        thinking_content = "\n".join(tool_commands.values())
        
        thinking_message = ChatMessage(
            role="assistant",
            content=thinking_content,
            tools_used=[],
            task_id=None
        )
        session.messages.append(thinking_message)
        
        # Broadcast thinking message
        await websocket_manager.broadcast_to_session(
            session_id,
            {
                "type": "message_added",
                "message": {
                    "id": thinking_message.id,
                    "role": thinking_message.role,
                    "content": thinking_message.content,
                    "timestamp": thinking_message.timestamp.isoformat(),
                    "tools_used": thinking_message.tools_used,
                    "task_id": thinking_message.task_id,
                    "is_thinking": True  # Mark as thinking message
                }
            }
        )
    
    # Add main assistant response to session
    assistant_message = ChatMessage(
        role="assistant", 
        content=content,
        tools_used=tools_used_list,
        task_id=completed_task.id if completed_task and tools_used_list else None
    )
    session.messages.append(assistant_message)
    
    # Notify WebSocket clients about new message
    await websocket_manager.broadcast_to_session(
        session_id,
        {
            "type": "message_added",
            "message": {
                "id": assistant_message.id,
                "role": assistant_message.role,
                "content": assistant_message.content,
                "timestamp": assistant_message.timestamp.isoformat(),
                "tools_used": assistant_message.tools_used,
                "task_id": assistant_message.task_id
            }
        }
    )
    
    # Only notify about task if tools were used
    if completed_task and tools_used_list:
        await websocket_manager.broadcast_to_session(
            session_id,
            {
                "type": "task_created",
                "task": completed_task.to_dict()
            }
        )
    
    return {
        "message": {
            "id": assistant_message.id,
            "role": assistant_message.role, 
            "content": assistant_message.content,
            "timestamp": assistant_message.timestamp.isoformat(),
            "tools_used": assistant_message.tools_used,
            "task_id": assistant_message.task_id
        }
    }


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Get all messages in a session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "tools_used": msg.tools_used,
                "task_id": msg.task_id
            }
            for msg in session.messages
        ]
    }

@app.get("/sessions/{session_id}/tasks", response_model=List[TaskResponse])
async def list_session_tasks(session_id: str):
    """List all tasks for a session (only tasks with tool usage)"""
    tasks = task_manager.get_session_tasks(session_id)
    # Only return tasks that actually used tools
    tool_tasks = [t for t in tasks if t.tools_used]
    return [TaskResponse.from_task(t) for t in tool_tasks]


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get a specific task"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.from_task(task)


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a running task"""
    success = await task_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already completed")
    return {"message": "Task cancelled successfully"}


# Agent endpoints
@app.get("/agents", response_model=List[AgentInfo])
async def list_available_agents():
    """List all available agents"""
    from cai.agents import get_available_agents
    
    available_agents = get_available_agents()
    agents = []
    
    for agent_name, agent_instance in available_agents.items():
        # Get agent description and tools
        description = getattr(agent_instance, 'description', '')
        tools = [tool.__name__ if hasattr(tool, '__name__') else str(tool) 
                for tool in getattr(agent_instance, 'tools', [])]
        
        agents.append(AgentInfo(
            name=agent_name,
            display_name=getattr(agent_instance, 'name', agent_name.replace('_', ' ').title()),
            description=description,
            tools=tools,
            capabilities=tools  # For now, use tools as capabilities
        ))
    
    return agents


@app.get("/models")
async def list_available_models():
    """List all available models"""
    import os
    
    # Get current model from environment or use default
    current_model = os.getenv("CAI_MODEL", "openrouter/z-ai/glm-4.5-air:free")
    
    # Common available models with their providers
    models = [
        {"id": "openrouter/z-ai/glm-4.5-air:free", "name": "GLM-4.5-Air (Free)", "provider": "openrouter"},
        {"id": "gpt-4o", "name": "GPT-4 Optimized", "provider": "openai"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai"},
        {"id": "claude-3-5-sonnet", "name": "Claude 3.5 Sonnet", "provider": "anthropic"},
        {"id": "claude-3-5-haiku", "name": "Claude 3.5 Haiku", "provider": "anthropic"},
        {"id": "deepseek-v3", "name": "DeepSeek V3", "provider": "deepseek"},
        {"id": "alias0", "name": "Alias0", "provider": "alias"},
        {"id": "qwen2.5:14b", "name": "Qwen 2.5 14B", "provider": "ollama"},
    ]
    
    # Add current model if not in list
    if current_model not in [m["id"] for m in models]:
        models.insert(0, {
            "id": current_model,
            "name": current_model.split("/")[-1] if "/" in current_model else current_model,
            "provider": "custom"
        })
    
    return {
        "models": models,
        "current": current_model
    }


# WebSocket endpoint for real-time updates
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket connection for real-time session updates"""
    session = session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    await websocket_manager.connect(websocket, session_id)
    
    try:
        while True:
            # Keep connection alive and handle any incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket, session_id)


# Error handlers
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "cai.web.backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
