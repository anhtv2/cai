"""
Data models for CAI Web Backend
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import uuid


class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionStatus(str, Enum):
    """Session status enumeration"""
    ACTIVE = "active"
    IDLE = "idle"
    TERMINATED = "terminated"


class AgentInfo(BaseModel):
    """Agent information model"""
    name: str
    display_name: str
    description: str
    tools: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)


class SessionCreate(BaseModel):
    """Request model for creating a session"""
    name: str
    agent_type: str
    model: str
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """Chat message in a session"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tools_used: List[str] = Field(default_factory=list)
    task_id: Optional[str] = None  # Link to task if tools were used

class Session(BaseModel):
    """Session model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    agent_type: str
    model: str
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    config: Dict[str, Any] = Field(default_factory=dict)
    agent: Optional[Any] = None  # Will hold the actual CAI agent instance
    messages: List[ChatMessage] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


class SessionResponse(BaseModel):
    """Response model for session data"""
    id: str
    name: str
    agent_type: str
    model: str
    status: str
    created_at: str
    updated_at: str
    task_count: int = 0
    
    @classmethod
    def from_session(cls, session: Session) -> "SessionResponse":
        return cls(
            id=session.id,
            name=session.name,
            agent_type=session.agent_type,
            model=session.model,
            status=session.status,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat()
        )


class MessageRequest(BaseModel):
    """Request model for sending a message"""
    content: str
    context: Optional[Dict[str, Any]] = None


class Task(BaseModel):
    """Task model representing an agent action"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    message: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    logs: List[Dict[str, Any]] = Field(default_factory=list)
    tools_used: List[str] = Field(default_factory=list)
    token_usage: Dict[str, int] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Store additional task data
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "message": self.message,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "logs": self.logs,
            "tools_used": self.tools_used,
            "token_usage": self.token_usage,
            "metadata": self.metadata
        }


class TaskResponse(BaseModel):
    """Response model for task data"""
    id: str
    session_id: str
    message: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    tools_used: List[str] = Field(default_factory=list)
    duration: Optional[float] = None
    
    @classmethod
    def from_task(cls, task: Task) -> "TaskResponse":
        duration = None
        if task.started_at and task.completed_at:
            duration = (task.completed_at - task.started_at).total_seconds()
        
        return cls(
            id=task.id,
            session_id=task.session_id,
            message=task.message,
            status=task.status,
            created_at=task.created_at.isoformat(),
            started_at=task.started_at.isoformat() if task.started_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
            result=task.result,
            error=task.error,
            tools_used=task.tools_used,
            duration=duration
        )


class WebSocketMessage(BaseModel):
    """WebSocket message model"""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
