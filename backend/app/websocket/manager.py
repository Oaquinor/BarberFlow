"""WebSocket manager for real-time features."""

from typing import Dict
from fastapi import WebSocket


class ConnectionManager:
    """
    Manages WebSocket connections.

    Handles real-time communication for:
    - Appointment updates
    - Barber status changes
    - Client check-ins
    - Live dashboard updates
    """

    def __init__(self):
        self.active_connections: Dict[int, list[WebSocket]] = {}

    async def connect(self, barbershop_id: int, websocket: WebSocket):
        """
        Connect client to barbershop room.

        Args:
            barbershop_id: Barbershop ID (room)
            websocket: WebSocket connection
        """
        await websocket.accept()

        if barbershop_id not in self.active_connections:
            self.active_connections[barbershop_id] = []

        self.active_connections[barbershop_id].append(websocket)

    def disconnect(self, barbershop_id: int, websocket: WebSocket):
        """
        Disconnect client from barbershop room.

        Args:
            barbershop_id: Barbershop ID
            websocket: WebSocket connection
        """
        if barbershop_id in self.active_connections:
            self.active_connections[barbershop_id].remove(websocket)

    async def broadcast(self, barbershop_id: int, message: dict):
        """
        Broadcast message to all clients in barbershop room.

        Args:
            barbershop_id: Barbershop ID
            message: Message to broadcast
        """
        if barbershop_id in self.active_connections:
            for connection in self.active_connections[barbershop_id]:
                await connection.send_json(message)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        Send message to specific client.

        Args:
            message: Message to send
            websocket: Target WebSocket connection
        """
        await websocket.send_json(message)


# Global connection manager instance
manager = ConnectionManager()
