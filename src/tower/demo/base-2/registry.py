import time
import threading

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