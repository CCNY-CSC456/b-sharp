# REQ-TOW-005
# models.py — defines what a "message" is.
# Every other file uses these field names, so we all have to agree on this.

# BaseModel comes from Pydantic (installed with FastAPI).
# It lets FastAPI automatically check incoming JSON against this shape.
from pydantic import BaseModel


class Message(BaseModel):
    # Every message must have these 3 fields, and each must be text.
    # If a request is missing one, FastAPI rejects it with an error before any of our code runs.
    sender: str      # who sent it:   "radar", "tower", or "command"
    recipient: str   # who it's for:  "radar", "tower", or "command"
    content: str     # the actual message, e.g. "AA123 at 5000ft hdg 270"
