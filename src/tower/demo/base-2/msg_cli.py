#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.request


def _post_json(url, payload, timeout_s=10):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url, timeout_s=10):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv):
    ap = argparse.ArgumentParser(description="CLI tool to send messages or query nodes via the primary coordinator.")
    ap.add_argument("--primary", default="http://127.0.0.1:9200", help="Primary coordinator URL")
    ap.add_argument("--list-nodes", action="store_true", help="List all currently active nodes registered with primary")
    ap.add_argument("--target", default=None, help="Target node_id (optional; omitted sends to all active nodes)")
    ap.add_argument("--sender", default="cli_user", help="Sender identity string")
    ap.add_argument("--msg", default=None, help="Message text content to send")

    args = ap.parse_args(argv)
    primary_url = args.primary.rstrip("/")

    if args.list-nodes:
        try:
            resp = _get_json(f"{primary_url}/nodes")
            if resp.get("ok"):
                nodes = resp.get("nodes", [])
                print(f"Active registered nodes ({len(nodes)}):")
                for n in nodes:
                    print(f"  - {n['node_id']} @ http://{n['host']}:{n['port']} (last seen: {n['last_seen']:.0f})")
            else:
                print(f"Error fetching nodes: {resp}", file=sys.stderr)
                return 1
        except Exception as e:
            print(f"Failed to connect to primary coordinator: {e}", file=sys.stderr)
            return 1
        return 0

    if not args.msg:
        print("Error: Must provide --msg <text> or use --list-nodes", file=sys.stderr)
        return 2

    payload = {
        "sender": args.sender,
        "target": args.target,
        "message": args.msg
    }

    try:
        resp = _post_json(f"{primary_url}/send", payload)
        if not resp.get("ok"):
            print(f"Error sending message: {resp.get('error')}", file=sys.stderr)
            return 1

        print("Message routing summary:")
        for res in resp.get("results", []):
            status = res.get("status")
            node = res.get("node_id")
            if status == "delivered":
                print(f"  [✓] Delivered to {node}")
            else:
                print(f"  [✗] Failed to reach {node}: {res.get('error')}")

    except Exception as e:
        print(f"Failed to dispatch message to primary: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))