#!/usr/bin/env python3
import json
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

# Import components directly from your refactored files
import primary_node
import secondary_node


def start_stoppable_registration_loop(primary_url, node_id, host, port, stop_event, interval_s=1):
    """Modified registration loop that checks a stop_event flag for clean teardown."""
    reg_url = primary_url.rstrip("/") + "/register"
    payload = {
        "node_id": node_id,
        "host": host,
        "port": port,
    }

    def loop():
        while not stop_event.is_set():
            payload["ts"] = time.time()
            try:
                secondary_node._post_json(reg_url, payload, timeout_s=1)
            except Exception:
                pass
            stop_event.wait(interval_s)

    th = Thread(target=loop, daemon=True)
    th.start()


class TestMessagingSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Spin up Primary and two Secondary nodes in background threads."""
        cls.primary_port = 9200
        cls.node1_port = 9101
        cls.node2_port = 9102

        cls.primary_url = f"http://127.0.0.1:{cls.primary_port}"
        cls.stop_heartbeats = Event()

        # 1. Start Primary Coordinator
        primary_node.REGISTRY = primary_node.Registry(ttl_s=10)
        cls.primary_server = ThreadingHTTPServer(
            ("127.0.0.1", cls.primary_port), primary_node.Handler
        )
        cls.primary_thread = Thread(target=cls.primary_server.serve_forever, daemon=True)
        cls.primary_thread.start()

        # 2. Start Secondary Node 1 ("node-alpha")
        cls.node1_server = ThreadingHTTPServer(
            ("127.0.0.1", cls.node1_port), secondary_node.Handler
        )
        cls.node1_thread = Thread(target=cls.node1_server.serve_forever, daemon=True)
        cls.node1_thread.start()

        secondary_node.NODE_META = {
            "node_id": "node-alpha",
            "bind_host": "127.0.0.1",
            "bind_port": cls.node1_port,
        }
        start_stoppable_registration_loop(
            cls.primary_url, "node-alpha", "127.0.0.1", cls.node1_port, cls.stop_heartbeats, interval_s=1
        )

        # 3. Start Secondary Node 2 ("node-beta")
        cls.node2_server = ThreadingHTTPServer(
            ("127.0.0.1", cls.node2_port), secondary_node.Handler
        )
        cls.node2_thread = Thread(target=cls.node2_server.serve_forever, daemon=True)
        cls.node2_thread.start()

        start_stoppable_registration_loop(
            cls.primary_url, "node-beta", "127.0.0.1", cls.node2_port, cls.stop_heartbeats, interval_s=1
        )

        # Give nodes time to send initial heartbeat registration
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        """Shut down HTTP servers and background loops cleanly."""
        # Signal registration loops to stop first
        cls.stop_heartbeats.set()
        time.sleep(0.1)

        cls.primary_server.shutdown()
        cls.node1_server.shutdown()
        cls.node2_server.shutdown()
        cls.primary_server.server_close()
        cls.node1_server.server_close()
        cls.node2_server.server_close()

    def _post_json(self, url, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get_json(self, url):
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ---------------------------------------------------------------
    # Test Cases
    # ---------------------------------------------------------------

    def test_01_nodes_registered(self):
        """Verify both nodes registered with the primary coordinator."""
        res = self._get_json(f"{self.primary_url}/nodes")
        self.assertTrue(res.get("ok"))
        nodes = {n["node_id"] for n in res.get("nodes", [])}
        self.assertIn("node-alpha", nodes)
        self.assertIn("node-beta", nodes)

    def test_02_send_targeted_message(self):
        """Verify targeted routing to a single node."""
        payload = {
            "sender": "test_suite",
            "target": "node-alpha",
            "message": "Direct message to Alpha",
        }
        res = self._post_json(f"{self.primary_url}/send", payload)
        self.assertTrue(res.get("ok"))

        results = res.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["node_id"], "node-alpha")
        self.assertEqual(results[0]["status"], "delivered")

    def test_03_send_broadcast_message(self):
        """Verify broadcasting to all active nodes when target is omitted."""
        payload = {
            "sender": "test_suite",
            "target": None,
            "message": "Broadcast message to all",
        }
        res = self._post_json(f"{self.primary_url}/send", payload)
        self.assertTrue(res.get("ok"))

        results = res.get("results", [])
        self.assertEqual(len(results), 2)
        delivered_nodes = {r["node_id"] for r in results if r["status"] == "delivered"}
        self.assertEqual(delivered_nodes, {"node-alpha", "node-beta"})

    def test_04_unknown_target_node(self):
        """Verify error response when routing to a non-existent node (cleanly handling HTTP 400)."""
        payload = {
            "sender": "test_suite",
            "target": "node-unknown",
            "message": "Hello ghost node",
        }
        try:
            self._post_json(f"{self.primary_url}/send", payload)
            self.fail("Expected HTTPError 400 was not raised")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 400)
            body = json.loads(err.read().decode("utf-8"))
            err.close()  # Cleanly close connection resource to prevent ResourceWarning
            self.assertFalse(body.get("ok"))
            self.assertIn("not active or registered", body.get("error", ""))


if __name__ == "__main__":
    unittest.main()