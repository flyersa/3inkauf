import json
import logging
from typing import Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections per shopping list."""

    def __init__(self):
        # {list_id: {user_id: WebSocket}}
        self.active_connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, list_id: str, user_id: str):
        await websocket.accept()
        if list_id not in self.active_connections:
            self.active_connections[list_id] = {}
        self.active_connections[list_id][user_id] = websocket
        logger.info(f"User {user_id} connected to list {list_id}")

    def disconnect(self, list_id: str, user_id: str):
        if list_id in self.active_connections:
            self.active_connections[list_id].pop(user_id, None)
            if not self.active_connections[list_id]:
                del self.active_connections[list_id]
        logger.info(f"User {user_id} disconnected from list {list_id}")

    async def broadcast(self, list_id: str, message: dict, exclude_user: Optional[str] = None):
        """Broadcast a message to all connections on a list, optionally excluding a user."""
        if list_id not in self.active_connections:
            return
        disconnected = []
        for user_id, ws in self.active_connections[list_id].items():
            if user_id == exclude_user:
                continue
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                disconnected.append(user_id)
        for uid in disconnected:
            self.disconnect(list_id, uid)


manager = ConnectionManager()
