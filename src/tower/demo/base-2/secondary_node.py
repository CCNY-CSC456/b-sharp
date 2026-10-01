#!/usr/bin/env python3
import argparse
import json
import os
import socket
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


from sundry import _post_json
from handler import Handler

from node_meta import NODE_META # NODE_META = {}


def _guess_local_ip_for(primary_url):
    try:
        u = urlparse(primary_url)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "https" else 80)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((host, port))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"





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
                print(f"[node {node_id}] heartbeat registration failed: {e}")
            time.sleep(interval_s)

    th = threading.Thread(target=loop, daemon=True)
    th.start()



def main():
    ap = argparse.ArgumentParser(description="Secondary messaging node.")
    ap.add_argument("--host", default="127.0.0.1", help="Bind host")
    ap.add_argument("--port", type=int, default=9100, help="Bind port")
    ap.add_argument("--node-id", default=None, help="Node ID (default: hostname)")
    ap.add_argument("--primary", default=None, help="Primary coordinator URL")
    ap.add_argument("--public-host", default=None, help="Advertised host")
    ap.add_argument("--register-interval", type=int, default=30, help="Heartbeat interval in seconds")

    args = ap.parse_args()

    node_id = args.node_id or os.uname().nodename

    advertised_host = args.public_host
    if args.primary and not advertised_host:
        advertised_host = _guess_local_ip_for(args.primary)
    if not advertised_host:
        advertised_host = "127.0.0.1"

    NODE_META.update({
        "node_id": node_id,
        "bind_host": args.host,
        "bind_port": args.port,
        "advertised_host": advertised_host,
        "advertised_port": args.port,
        "registered_to": args.primary,
    })

    if args.primary:
        start_registration_loop(
            args.primary,
            node_id=node_id,
            host=advertised_host,
            port=args.port,
            interval_s=max(5, int(args.register_interval)),
        )

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[node] node_id={node_id} listening on http://{args.host}:{args.port}")
    if args.primary:
        print(f"[node] registering to primary at {args.primary}")
    print("  GET  /health")
    print("  GET  /info")
    print("  POST /message")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[node] Shutting down graceful...", flush=True)
        httpd.shutdown()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()