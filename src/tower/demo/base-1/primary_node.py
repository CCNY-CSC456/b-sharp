#!/usr/bin/env python3
import argparse
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class Registry:
    def __init__(self, ttl_s=120):
        self.ttl_s = ttl_s
        self.lock = threading.Lock()
        self.nodes = {}

    def upsert(self, node):
        node_id = str(node["node_id"])
        now = time.time()
        record = {
            "node_id": node_id,
            "host": str(node["host"]),
            "port": int(node["port"]),
            "last_seen": float(node.get("ts", now)),
            "registered_at": now,
        }
        with self.lock:
            if node_id in self.nodes:
                record["registered_at"] = self.nodes[node_id].get("registered_at", now)
            self.nodes[node_id] = record
            return record

    def active_nodes(self):
        now = time.time()
        with self.lock:
            stale = [nid for nid, rec in self.nodes.items() if (now - float(rec.get("last_seen", 0))) > self.ttl_s]
            for nid in stale:
                del self.nodes[nid]
            return list(self.nodes.values())

    def get_node(self, node_id):
        active = self.active_nodes()
        for n in active:
            if n["node_id"] == node_id:
                return n
        return None


REGISTRY = Registry(ttl_s=120)


def _post_json(url, payload, timeout_s=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def route_message(sender, target_node_id, message):
    if target_node_id:
        node = REGISTRY.get_node(target_node_id)
        if not node:
            raise ValueError(f"Target node '{target_node_id}' is not active or registered")
        targets = [node]
    else:
        targets = REGISTRY.active_nodes()
        if not targets:
            raise ValueError("No active nodes available to receive message")

    delivery_results = []
    for node in targets:
        url = f"http://{node['host']}:{node['port']}/message"
        payload = {
            "sender": sender,
            "message": message
        }
        try:
            resp = _post_json(url, payload, timeout_s=5)
            delivery_results.append({
                "node_id": node["node_id"],
                "status": "delivered",
                "response": resp
            })
        except Exception as e:
            delivery_results.append({
                "node_id": node["node_id"],
                "status": "failed",
                "error": str(e)
            })

    return delivery_results


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
                results = route_message(sender, target, message)
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