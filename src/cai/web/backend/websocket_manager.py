"""
WebSocket Manager for CAI Web Backend
"""
import asyncio
from typing import Dict, List, Set, Any
from fastapi import WebSocket
import json


class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        # Maps session_id to list of WebSocket connections
        self.connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept and register a WebSocket connection"""
        await websocket.accept()
        
        async with self._lock:
            if session_id not in self.connections:
                self.connections[session_id] = []
            self.connections[session_id].append(websocket)
        
        # Send initial connection confirmation
        await self._send_to_websocket(websocket, {
            "type": "connected",
            "session_id": session_id
        })
    
    def disconnect(self, websocket: WebSocket, session_id: str):
        """Remove a WebSocket connection"""
        if session_id in self.connections:
            self.connections[session_id].remove(websocket)
            if not self.connections[session_id]:
                del self.connections[session_id]
    
    async def _send_to_websocket(self, websocket: WebSocket, data: Dict[str, Any]):
        """Send data to a single WebSocket connection"""
        try:
            await websocket.send_json(data)
        except Exception:
            # Connection might be closed
            pass
    
    async def broadcast_to_session(self, session_id: str, data: Dict[str, Any]):
        """Broadcast data to all connections for a session"""
        if session_id in self.connections:
            # Create tasks for all sends
            tasks = [
                self._send_to_websocket(ws, data)
                for ws in self.connections[session_id]
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast_to_all(self, data: Dict[str, Any]):
        """Broadcast data to all connected clients"""
        tasks = []
        for websockets in self.connections.values():
            for ws in websockets:
                tasks.append(self._send_to_websocket(ws, data))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def disconnect_all(self):
        """Disconnect all WebSocket connections"""
        for session_id, websockets in self.connections.items():
            for ws in websockets:
                try:
                    await ws.close()
                except Exception:
                    pass
        self.connections.clear()


# Global instance
websocket_manager = WebSocketManager()
