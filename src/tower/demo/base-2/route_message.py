from sundry import _post_json

def route_message(sender, target_node_id, message, registry=None):
    # Fall back to global REGISTRY if non-default parameter isn't passed
    reg = registry # or REGISTRY

    if not reg:
      raise ValueError("No registry")

    if target_node_id:
        node = reg.get_node(target_node_id)
        if not node:
            raise ValueError(f"Target node '{target_node_id}' is not active or registered")
        targets = [node]
    else:
        targets = reg.active_nodes()
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