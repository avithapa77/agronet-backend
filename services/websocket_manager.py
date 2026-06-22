"""
websocket_manager.py

Keeps track of every browser tab connected via WebSocket and
provides a broadcast() function that the rest of the app calls
whenever something changes (new sensor reading, mission dispatched, etc).
"""

import asyncio
import json
from typing import Set
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)

    async def broadcast(self, message: dict):
        """Send a message to every connected browser tab."""
        if not self.connections:
            return
        data = json.dumps(message)
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self.connections -= dead


# Single shared instance — imported everywhere
manager = WebSocketManager()
