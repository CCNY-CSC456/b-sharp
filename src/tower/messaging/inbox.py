# REQ-TOW-002
# inbox.py — the "pick-up window." Handles CHECKING a subsystem's messages.
# Endpoint: GET /messages?recipient=tower

from fastapi import APIRouter
from src.tower.messaging.db import get_messages      # the function that reads from the database

# Same idea as in send.py: a group of endpoints that main.py plugs in.
router = APIRouter()


# This runs whenever someone sends a GET request to /messages.
@router.get("/messages")
def inbox(recipient: str):
    # FastAPI pulls `recipient` out of the URL for us.
    # e.g. /messages?recipient=tower  ->  recipient = "tower"
    # If the URL has no ?recipient=..., FastAPI returns a 422 error automatically.
    return get_messages(recipient)  # the list of messages goes back as JSON
