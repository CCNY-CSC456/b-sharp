# REQ-TOW-005
# send.py — the "drop-off window." Handles SENDING a message.
# Endpoint: POST /messages

from fastapi import APIRouter
from src.tower.messaging.models import Message       # the message shape (sender, recipient, content)
from src.tower.messaging.db import save_message      # the function that writes to the database

# A router is a mini group of endpoints that main.py plugs into the app.
# This is what lets each endpoint live in its own file.
router = APIRouter()


# This runs whenever someone sends a POST request to /messages.
@router.post("/messages")
def send(msg: Message):
    # By the time we get here, FastAPI has already turned the JSON body
    # into a Message object and checked that all 3 fields are there.
    save_message(msg.sender, msg.recipient, msg.content)
    # Whatever we return gets sent back to the sender as JSON.
    return {"status": "sent"}
