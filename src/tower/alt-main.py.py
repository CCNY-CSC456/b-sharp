# src/tower/messaging/main.py
import json
import threading
import time
import urllib.request
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.tower.messaging.db import init_db
from src.tower.messaging import send, inbox

PRIMARY_URL = "http://127.0.0.1:9200"
NODE_ID = "tower_fastapi_node"
HOST = "127.0.0.1"
PORT = 8000  # Default port when running uvicorn


def _post_json(url, payload, timeout_s=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def start_registration_loop(primary_url, node_id, host, port, interval_s=30):
    reg_url = primary_url.rstrip("/") + "/register"
    payload = {
        "node_id": node_id,
        "host": host,
        "port": port,
    }

    def loop():
        while True:
            payload["ts"] = time.time()
            try:
                _post_json(reg_url, payload, timeout_s=5)
            except Exception as e:
                print(f"[{node_id}] Heartbeat registration failed: {e}")
            time.sleep(interval_s)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the local SQLite table
    init_db()
    # Start registration loop thread when server starts
    start_registration_loop(PRIMARY_URL, NODE_ID, HOST, PORT, interval_s=30)
    yield


app = FastAPI(lifespan=lifespan)

# Attach routes
app.include_router(send.router)
app.include_router(inbox.router)