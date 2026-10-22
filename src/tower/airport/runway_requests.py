import json

from src.tower.messaging.db import init_db as init_messages_db, save_message, get_messages
from src.tower.airport.airport_repo import assign_runway, free_runway, mark_processed, is_processed

REQUEST_LANDING = "REQUEST_LANDING"
REQUEST_TAKEOFF = "REQUEST_TAKEOFF"
LANDED = "LANDED"
DEPARTED = "DEPARTED"
RUNWAY_ASSIGNED = "RUNWAY_ASSIGNED"
NO_RUNWAY = "NO_RUNWAY"
FREED = "FREED"

RADAR_MESSAGES = (REQUEST_LANDING, REQUEST_TAKEOFF, LANDED, DEPARTED)


def read_tower_inbox():
    init_messages_db()
    return get_messages("tower")


def send_to_radar(content):
    init_messages_db()
    save_message("tower", "radar", content)


def read_json(message):
    try:
        content = json.loads(message["content"])
    except (ValueError, TypeError):
        return None
    return content if isinstance(content, dict) else None


def read_request(message):
    if message.get("sender") != "radar":
        return None
    request = read_json(message)
    if request is None or not isinstance(request.get("aircraft_id"), str):
        return None
    if request.get("type") not in RADAR_MESSAGES:
        return None
    return request


def process_landed(conn, airport_id, aircraft_id, request):
    return None


def process_departed(conn, airport_id, aircraft_id, request):
    runway_id = free_runway(conn, airport_id, aircraft_id)
    if runway_id is not None:
        return {"type": FREED, "aircraft_id": aircraft_id, "runway_id": runway_id}
    return None


def process_clearance(conn, airport_id, aircraft_id, request):
    req_type = request["type"]
    runway_id = assign_runway(conn, airport_id, aircraft_id)

    if runway_id is None:
        reply = {"type": NO_RUNWAY, "aircraft_id": aircraft_id}
    else:
        reply = {"type": RUNWAY_ASSIGNED, "aircraft_id": aircraft_id, "runway_id": runway_id}

    reply["request"] = req_type
    reply["request_timestamp"] = request.get("timestamp")
    return reply


HANDLERS = {
    LANDED: process_landed,
    DEPARTED: process_departed,
    REQUEST_LANDING: process_clearance,
    REQUEST_TAKEOFF: process_clearance,
}


def answer_requests(conn, airport_id, get=read_tower_inbox, sent_to_radar=None, send=send_to_radar):
    results = []

    for aircraft_id, request in newest_per_plane(get()).items():
        req_type = request["type"]
        req_timestamp = request.get("timestamp")

        msg_key = f"{aircraft_id}:{req_type}:{req_timestamp}"
        if is_processed(conn, msg_key):
            continue

        handler = HANDLERS.get(req_type)
        if not handler:
            continue

        result = handler(conn, airport_id, aircraft_id, request)

        if result is not None:
            if result.get("type") != FREED:
                send(json.dumps(result))
            results.append(result)

        mark_processed(conn, msg_key)

    return results


def newest_per_plane(inbox):
    newest = {}
    for message in inbox:
        request = read_request(message)
        if request is not None:
            newest[request["aircraft_id"]] = request
    return newest