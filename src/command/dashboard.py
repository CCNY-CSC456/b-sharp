"""REQ-OPS-001 / REQ-OPS-002: airport visibility and Tower messaging."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sqlite3

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from src.command.airport import get_airport_state
from src.tower.messaging import inbox, send
from src.tower.messaging.db import init_db


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app):
    # Keep the airport visible if Tower messaging cannot initialize.
    try:
        init_db()
    except sqlite3.Error:
        logger.warning("Tower messaging could not initialize", exc_info=True)
    yield


app = FastAPI(title="Command Visibility Dashboard", lifespan=lifespan)
app.include_router(send.router)
app.include_router(inbox.router)


@app.exception_handler(sqlite3.Error)
async def database_unavailable(_request, _error):
    """Let the page display degraded data links without exposing DB details."""
    return JSONResponse(status_code=503, content={"detail": "Data temporarily unavailable. Try again shortly."})


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Serve the airport and Tower messaging dashboard."""
    page = Path(__file__).with_name("dashboard.html")
    return page.read_text(encoding="utf-8")


@app.get("/api/airport")
def airport_state():
    """Return the airport and runway snapshot."""
    return get_airport_state()
