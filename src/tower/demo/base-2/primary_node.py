#!/usr/bin/env python3
import argparse
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from sundry import _post_json
from registry import Registry
from route_message import route_message


REGISTRY = Registry(ttl_s=120)


class Handler(BaseHTTPRequestHandler):
    server_version = "MessagePrimary/1.0"

    def _send_json(self, obj, code=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._send_json({"ok": True, "status": "healthy"})
        if parsed.path == "/nodes":
            nodes = REGISTRY.active_nodes()
            nodes.sort(key=lambda n: n["node_id"])
            return self._send_json({"ok": True, "nodes": nodes, "ttl_s": REGISTRY.ttl_s})
        return self._send_json({"ok": False, "error": "not found"}, code=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            return self._send_json({"ok": False, "error": "invalid content-length"}, code=400)

        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception as e:
            return self._send_json({"ok": False, "error": f"bad json: {e}"}, code=400)

        if parsed.path == "/register":
            for k in ("node_id", "host", "port"):
                if k not in payload:
                    return self._send_json({"ok": False, "error": f"missing field: {k}"}, code=400)
            rec = REGISTRY.upsert(payload)
            print(f"[primary] Registered node: {rec['node_id']} ({rec['host']}:{rec['port']})")
            return self._send_json({"ok": True, "node": rec})

        if parsed.path == "/send":
            sender = payload.get("sender", "client")
            target = payload.get("target", None)
            message = payload.get("message", "")

            if not message:
                return self._send_json({"ok": False, "error": "message payload cannot be empty"}, code=400)

            try:
                # results = route_message(sender, target, message)
                results = route_message(sender, target, message, REGISTRY)
                return self._send_json({"ok": True, "results": results}, code=200)
            except Exception as e:
                return self._send_json({"ok": False, "error": str(e)}, code=400)

        return self._send_json({"ok": False, "error": "not found"}, code=404)

    def log_message(self, fmt, *args):
        return


def main():
    ap = argparse.ArgumentParser(description="Primary message routing coordinator.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9200)
    ap.add_argument("--ttl", type=int, default=120, help="Node registration TTL in seconds")
    args = ap.parse_args()

    global REGISTRY
    REGISTRY = Registry(ttl_s=max(10, int(args.ttl)))

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[primary] listening on http://{args.host}:{args.port}")
    print("  GET  /health")
    print("  GET  /nodes")
    print("  POST /register")
    print("  POST /send")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[primary] Shutting down gracefully...", flush=True)
        httpd.shutdown()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()