"""WebSocket server for real-time communication with frontend."""

import asyncio
import json
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from app.utils.logger import app_logger


class WebSocketManager:
    """Manages WebSocket connections and message routing."""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}  # conversation_id -> set of connections
        self.connection_conversations: Dict[WebSocket, str] = {}  # connection -> conversation_id
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, conversation_id: Optional[str] = None):
        """Accept a WebSocket connection and optionally join a conversation."""
        await websocket.accept()
        
        async with self._lock:
            if conversation_id:
                if conversation_id not in self.active_connections:
                    self.active_connections[conversation_id] = set()
                self.active_connections[conversation_id].add(websocket)
                self.connection_conversations[websocket] = conversation_id
                app_logger.info(f"WebSocket connected to conversation {conversation_id}")
            else:
                # Connection without conversation (will join later)
                self.connection_conversations[websocket] = None
                app_logger.info("WebSocket connected (no conversation yet)")
    
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            conversation_id = self.connection_conversations.get(websocket)
            if conversation_id and conversation_id in self.active_connections:
                self.active_connections[conversation_id].discard(websocket)
                if not self.active_connections[conversation_id]:
                    del self.active_connections[conversation_id]
                app_logger.info(f"WebSocket disconnected from conversation {conversation_id}")
            
            if websocket in self.connection_conversations:
                del self.connection_conversations[websocket]
    
    async def join_conversation(self, websocket: WebSocket, conversation_id: str):
        """Join a WebSocket to a conversation."""
        async with self._lock:
            # Leave current conversation if any
            old_conversation = self.connection_conversations.get(websocket)
            if old_conversation and old_conversation in self.active_connections:
                self.active_connections[old_conversation].discard(websocket)
                if not self.active_connections[old_conversation]:
                    del self.active_connections[old_conversation]
            
            # Join new conversation
            if conversation_id not in self.active_connections:
                self.active_connections[conversation_id] = set()
            self.active_connections[conversation_id].add(websocket)
            self.connection_conversations[websocket] = conversation_id
            app_logger.info(f"WebSocket joined conversation {conversation_id}")
    
    async def send_to_conversation(self, conversation_id: str, message: dict):
        """Send a message to all connections in a conversation."""
        if conversation_id not in self.active_connections:
            return
        
        disconnected = set()
        for websocket in self.active_connections[conversation_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                app_logger.error(f"Failed to send to WebSocket: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected sockets
        if disconnected:
            async with self._lock:
                for websocket in disconnected:
                    self.active_connections[conversation_id].discard(websocket)
                    if websocket in self.connection_conversations:
                        del self.connection_conversations[websocket]
                
                if not self.active_connections[conversation_id]:
                    del self.active_connections[conversation_id]

    async def broadcast_to_all(self, message: dict):
        """Send a message to EVERY connected socket, whatever room it is in.

        Used for owner-wide signals like conversation_activity, so UIs on
        other devices refresh their conversation lists / follow the owner's
        active chat even though they are parked in a different room."""
        disconnected = set()
        for websocket in list(self.connection_conversations.keys()):
            try:
                await websocket.send_json(message)
            except Exception as e:
                app_logger.error(f"Failed to broadcast to WebSocket: {e}")
                disconnected.add(websocket)

        if disconnected:
            async with self._lock:
                for websocket in disconnected:
                    conversation_id = self.connection_conversations.get(websocket)
                    if conversation_id and conversation_id in self.active_connections:
                        self.active_connections[conversation_id].discard(websocket)
                        if not self.active_connections[conversation_id]:
                            del self.active_connections[conversation_id]
                    if websocket in self.connection_conversations:
                        del self.connection_conversations[websocket]

    
    async def send_to_connection(self, websocket: WebSocket, message: dict):
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            app_logger.error(f"Failed to send to WebSocket: {e}")
            await self.disconnect(websocket)
    
    def get_conversation_connections(self, conversation_id: str) -> Set[WebSocket]:
        """Get all connections in a conversation."""
        return self.active_connections.get(conversation_id, set())
    
    def get_active_conversations(self) -> list:
        """Get list of active conversation IDs."""
        return list(self.active_connections.keys())

    async def broadcast_to_conversation(self, conversation_id: str, message: dict):
        """Alias for send_to_conversation for backward compatibility."""
        await self.send_to_conversation(conversation_id, message)

    async def send_audio_to_conversation(self, conversation_id: str, audio_bytes: bytes):
        """Send binary audio data to all connections in a conversation."""
        if conversation_id not in self.active_connections:
            return

        disconnected = set()
        for websocket in self.active_connections[conversation_id]:
            try:
                await websocket.send_bytes(audio_bytes)
            except Exception as e:
                app_logger.error(f"Failed to send audio to WebSocket: {e}")
                disconnected.add(websocket)

        if disconnected:
            async with self._lock:
                for websocket in disconnected:
                    self.active_connections[conversation_id].discard(websocket)
                    if websocket in self.connection_conversations:
                        del self.connection_conversations[websocket]

                if not self.active_connections[conversation_id]:
                    del self.active_connections[conversation_id]


# Global WebSocket manager instance
ws_manager = WebSocketManager()
