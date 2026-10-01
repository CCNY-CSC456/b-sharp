
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from node_meta import NODE_META
from sundry import _send_json

# # class Handler(BaseHTTPRequestHandler):
# #     server_version = "MessageNode/1.0"
# #
# #     def _send_json(self, obj, code=200):
# #         data = json.dumps(obj).encode("utf-8")
# #         self.send_response(code)
# #         self.send_header("Content-Type", "application/json")
# #         self.send_header("Content-Length", str(len(data)))
# #         self.end_headers()
# #         self.wfile.write(data)
# #
# #     def do_GET(self):
# #         parsed = urlparse(self.path)
# #         if parsed.path == "/health":
# #             return self._send_json({"ok": True, "status": "healthy"})
# #         if parsed.path == "/info":
# #             return self._send_json({"ok": True, "node": NODE_META})
# #         return self._send_json({"ok": False, "error": "not found"}, code=404)
# #
# #     def do_POST(self):
# #         parsed = urlparse(self.path)
# #         if parsed.path != "/message":
# #             return self._send_json({"ok": False, "error": "not found"}, code=404)
# #
# #         try:
# #             length = int(self.headers.get("Content-Length", "0"))
# #         except Exception:
# #             return self._send_json({"ok": False, "error": "invalid content-length"}, code=400)
# #
# #         if length <= 0:
# #             return self._send_json({"ok": False, "error": "empty body"}, code=400)
# #
# #         body = self.rfile.read(length)
# #         try:
# #             payload = json.loads(body.decode("utf-8"))
# #         except Exception as e:
# #             return self._send_json({"ok": False, "error": f"bad json: {e}"}, code=400)
# #
# #         sender = payload.get("sender", "unknown")
# #         message = payload.get("message", "")
# #
# #         print(f"\n[RECEIVED MESSAGE] From: {sender} | Content: {message}\n", flush=True)
# #
# #         return self._send_json({"ok": True, "node_id": NODE_META.get("node_id"), "status": "delivered"})
# #
# #     def log_message(self, fmt, *args):
# #         return


class Handler(BaseHTTPRequestHandler):
    server_version = "MessageNode/1.0"



    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return _send_json(self,{"ok": True, "status": "healthy"})
        if parsed.path == "/info":
            return _send_json(self,{"ok": True, "node": NODE_META})
        return _send_json(self,{"ok": False, "error": "not found"}, code=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/message":
            return _send_json(self,{"ok": False, "error": "not found"}, code=404)

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            return _send_json(self,{"ok": False, "error": "invalid content-length"}, code=400)

        if length <= 0:
            return _send_json(self,{"ok": False, "error": "empty body"}, code=400)

        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            return _send_json(self,{"ok": False, "error": f"bad json: {e}"}, code=400)

        sender = payload.get("sender", "unknown")
        message = payload.get("message", "")

        print(f"\n[RECEIVED MESSAGE] From: {sender} | Content: {message}\n", flush=True)

        return _send_json(self,{"ok": True, "node_id": NODE_META.get("node_id"), "status": "delivered"})

    def log_message(self, fmt, *args):
        return