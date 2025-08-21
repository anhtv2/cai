"""
Session Manager for CAI Web Backend
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

from .models import Session, SessionStatus
from ...sdk.agents import Agent
from ...agents import get_agent_by_name, get_available_agents


class SessionManager:
    """Manages CAI sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
    
    async def create_session(
        self,
        agent_type: str,
        model: str,
        name: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Session:
        """Create a new CAI session with an agent"""
        async with self._lock:
            # Create the agent based on type
            agent = self._create_agent(agent_type, model, config or {})
            
            # Create session
            session = Session(
                name=name,
                agent_type=agent_type,
                model=model,
                config=config or {},
                agent=agent
            )
            
            self.sessions[session.id] = session
            return session
    
    def _create_agent(
        self,
        agent_type: str,
        model: str,
        config: Dict[str, Any]
    ) -> Agent:
        """Create a CAI agent instance"""
        import os
        
        try:
            # Set the model as environment variable for the agent creation
            original_model = os.environ.get("CAI_MODEL")
            os.environ["CAI_MODEL"] = model
            
            try:
                # Use the agent factory system to create a new agent instance
                agent = get_agent_by_name(
                    agent_name=agent_type,
                    model_override=model,
                    agent_id=f"web-{agent_type}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
                )
            finally:
                # Restore original model environment variable
                if original_model is not None:
                    os.environ["CAI_MODEL"] = original_model
                elif "CAI_MODEL" in os.environ:
                    del os.environ["CAI_MODEL"]
            
            # Apply custom configuration if provided
            if hasattr(agent, 'model') and agent.model:
                if config.get("temperature") is not None:
                    if hasattr(agent.model, 'temperature'):
                        agent.model.temperature = config["temperature"]
                
                if config.get("max_tokens") is not None:
                    if hasattr(agent.model, 'max_tokens'):
                        agent.model.max_tokens = config["max_tokens"]
                
                if config.get("stream") is not None:
                    if hasattr(agent.model, 'stream'):
                        agent.model.stream = config["stream"]
            
            return agent
            
        except ValueError as e:
            # If agent type not found, provide helpful error
            available_agents = get_available_agents()
            raise ValueError(
                f"Unknown agent type: {agent_type}. "
                f"Available agents: {', '.join(available_agents.keys())}"
            ) from e
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID"""
        return self.sessions.get(session_id)
    
    def get_all_sessions(self) -> List[Session]:
        """Get all active sessions"""
        return list(self.sessions.values())
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        async with self._lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                session.status = SessionStatus.TERMINATED
                del self.sessions[session_id]
                return True
            return False
    
    async def update_session_activity(self, session_id: str):
        """Update session last activity timestamp"""
        if session_id in self.sessions:
            self.sessions[session_id].updated_at = datetime.utcnow()
    
    def add_to_history(self, session_id: str, entry: Dict[str, Any]):
        """Add an entry to session history"""
        if session_id in self.sessions:
            self.sessions[session_id].history.append({
                **entry,
                "timestamp": datetime.utcnow().isoformat()
            })
