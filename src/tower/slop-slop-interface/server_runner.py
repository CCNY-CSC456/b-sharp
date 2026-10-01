"""
server_runner.py — Black-box process abstraction layer for Tower Messaging backends.

This module leaves both original backend implementations untouched and manages them
strictly via subprocess execution and HTTP health checks.
"""

import abc
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Optional


class ServerProcess(abc.ABC):
    """Abstract lifecycle interface for managing a messaging backend instance."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.host = host
        self.port = port
        self.process: Optional[subprocess.Popen] = None

    @property
    def base_url(self) -> str:
        """Returns the base HTTP URL of the running service."""
        return f"http://{self.host}:{self.port}"

    @abc.abstractmethod
    def _build_command(self) -> list[str]:
        """Constructs the command-line array to launch the backend process."""
        pass

    def start(self, timeout: float = 5.0) -> None:
        """Launches the backend as a background process and waits for it to listen."""
        if self.is_running():
            return

        cmd = self._build_command()
        # Launch backend process independently
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Poll until the server responds to HTTP health checks
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_healthy():
                print(f"[{self.__class__.__name__}] Service ready at {self.base_url}")
                return
            time.sleep(0.1)

        self.stop()
        raise RuntimeError(
            f"[{self.__class__.__name__}] Failed to start within {timeout}s"
        )

    def stop(self) -> None:
        """Terminates the backend process cleanly."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            print(f"[{self.__class__.__name__}] Server stopped.")
        self.process = None

    def is_running(self) -> bool:
        """Checks if the subprocess is still actively executing."""
        return self.process is not None and self.process.poll() is None

    def is_healthy(self) -> str:
        """Verifies if the HTTP server is actively receiving requests."""
        try:
            # Check endpoint response (422 expected without recipient parameter, proving server is up)
            req = urllib.request.Request(f"{self.base_url}/messages")
            with urllib.request.urlopen(req) as response:
                return response.status in (200, 422)
        except urllib.error.HTTPError as e:
            return e.code in (200, 422)
        except urllib.error.URLError:
            return False


# =====================================================================
# Concrete Black-Box Adapters
# =====================================================================


class FastAPIServerProcess(ServerProcess):
    """Adapter wrapping the original FastAPI multi-file repository architecture.

    Assumes the original repo layout: src/tower/messaging/main.py
    Executed via: uvicorn src.tower.messaging.main:app
    """

    def _build_command(self) -> list[str]:
        return [
            sys.executable,
            "-m",
            "uvicorn",
            "src.tower.messaging.main:app",
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]


class StdlibServerProcess(ServerProcess):
    """Adapter wrapping the original single-file Standard Library script.

    Assumes file path: slopbox_server.py (or whichever file path contains the script).
    Executed via: python3 <script_path>
    """

    def __init__(
        self,
        script_path: str = "slopbox_server.py",
        host: str = "127.0.0.1",
        port: int = 8000,
    ):
        self.script_path = script_path
        super().__init__(host=host, port=port)

    def _build_command(self) -> list[str]:
        return [sys.executable, self.script_path]