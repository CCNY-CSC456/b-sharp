# src/tower/messaging/send.py
from fastapi import APIRouter
from pydantic import BaseModel
from src.tower.messaging.models import Message
from src.tower.messaging.db import save_message

router = APIRouter()


class NodeMessagePayload(BaseModel):
    sender: str = "unknown"
    message: str = ""


# System A's original endpoint
@router.post("/messages")
def send(msg: Message):
    save_message(msg.sender, msg.recipient, msg.content)
    return {"status": "sent"}


# System B's incoming node route
@router.post("/message")
def receive_from_primary(payload: NodeMessagePayload):
    # Save incoming message from System B into the local database
    save_message(sender=payload.sender, recipient="tower", content=payload.message)
    # Return the exact JSON structure System B expects from a secondary node
    return {
        "ok": True,
        "node_id": "tower_fastapi_node",
        "status": "delivered"
    }