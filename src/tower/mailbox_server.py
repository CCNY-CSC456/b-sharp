#!/usr/bin/env python3

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB_FILE = "messages.db"


def init_db(db_path=DB_FILE):
    """Create the messages table if it does not exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS messages (sender TEXT, recipient TEXT, content TEXT)"
    )
    conn.commit()
    conn.close()


def save_message(sender, recipient, content, db_path=DB_FILE):
    """Save a single message to SQLite."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?)", (sender, recipient, content)
    )
    conn.commit()
    conn.close()


def get_messages(recipient, db_path=DB_FILE):
    """Retrieve all messages for a specific recipient."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT sender, recipient, content FROM messages WHERE recipient = ?",
        (recipient,),
    ).fetchall()
    conn.close()
    return [{"sender": s, "recipient": r, "content": c} for s, r, c in rows]


class MailboxHandler(BaseHTTPRequestHandler):
    server_version = "MailboxServer/1.0"
    db_path = DB_FILE

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)

        # GET /messages?recipient=<name>
        if parsed.path == "/messages":
            query_params = parse_qs(parsed.query)
            recipients = query_params.get("recipient")

            if not recipients or not recipients[0].strip():
                return self._send_json(
                    {"error": "Missing required query parameter 'recipient'"},
                    code=422,
                )

            recipient = recipients[0].strip()
            messages = get_messages(recipient, db_path=self.db_path)
            return self._send_json(messages, code=200)

        return self._send_json({"error": "Not Found"}, code=404)

    def do_POST(self):
        parsed = urlparse(self.path)

        # POST /messages
        if parsed.path == "/messages":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send_json({"error": "Invalid Content-Length"}, code=400)

            if length <= 0:
                return self._send_json({"error": "Empty body"}, code=400)

            raw_body = self.rfile.read(length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                return self._send_json({"error": f"Invalid JSON: {e}"}, code=400)

            # Replicate Pydantic field validation
            required_fields = ["sender", "recipient", "content"]
            missing = [f for f in required_fields if f not in payload]
            if missing:
                return self._send_json(
                    {"error": f"Missing required fields: {', '.join(missing)}"},
                    code=422,
                )

            for field in required_fields:
                if not isinstance(payload[field], str):
                    return self._send_json(
                        {"error": f"Field '{field}' must be a string"},
                        code=422,
                    )

            save_message(
                payload["sender"],
                payload["recipient"],
                payload["content"],
                db_path=self.db_path,
            )
            return self._send_json({"status": "sent"}, code=200)

        return self._send_json({"error": "Not Found"}, code=404)

    def log_message(self, fmt, *args):
        # Silence default standard error logging for cleaner output
        return


def main():
    init_db()
    server_address = ("127.0.0.1", 8000)
    httpd = ThreadingHTTPServer(server_address, MailboxHandler)
    print("Mailbox server running on http://127.0.0.1:8000")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.shutdown()


if __name__ == "__main__":
    main()