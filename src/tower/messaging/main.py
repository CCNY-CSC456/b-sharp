# REQ-TOW-002
# main.py — the entry point. This is the file uvicorn runs:
#   uvicorn src.tower.messaging.main:app --reload   (run from the repo root)
# (src.tower.messaging.main = this file, "app" = the app variable below)
# It has no real logic; it just wires the other files together.

from fastapi import FastAPI
from src.tower.messaging.db import init_db
from src.tower.messaging import send    # our POST /messages endpoint
from src.tower.messaging import inbox   # our GET /messages endpoint

# Make sure the messages table exists before the server starts taking requests.
init_db()

# Create the server itself.
app = FastAPI()

# Plug in the endpoints from the other files.
# Without these two lines, the server would run but have no endpoints.
app.include_router(send.router)
app.include_router(inbox.router)
