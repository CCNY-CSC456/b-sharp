"""
example_usage.py — Demonstrates using the ServerProcess abstraction.
"""

# I HAVE NO IDEA IF THIS WORKS

import json
import os
import urllib.request
from server_runner import FastAPIServerProcess, ServerProcess, StdlibServerProcess


def test_messaging_flow(server: ServerProcess) -> None:
    """Agnostic client test function operating over HTTP."""
    server.start()

    try:
        # 1. Send POST request
        payload = json.dumps(
            {
                "sender": "radar",
                "recipient": "tower",
                "content": "AA123 at 5000ft hdg 270",
            }
        ).encode("utf-8")

        post_req = urllib.request.Request(
            f"{server.base_url}/messages",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(post_req) as resp:
            print("POST /messages Response:", resp.status, resp.read().decode())

        # 2. Send GET request
        get_req = urllib.request.Request(f"{server.base_url}/messages?recipient=tower")
        with urllib.request.urlopen(get_req) as resp:
            print("GET /messages Response:", resp.status, resp.read().decode())

    finally:
        server.stop()


if __name__ == "__main__":
    # Toggle which backend to run using environment variables
    backend = os.getenv("BACKEND_TYPE", "stdlib").lower()

    runner: ServerProcess
    if backend == "fastapi":
        runner = FastAPIServerProcess(port=8000)
    else:
        runner = StdlibServerProcess(script_path="slopbox_server.py", port=8000)

    test_messaging_flow(runner)