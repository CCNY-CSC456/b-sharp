# REQ-TOW-008, REQ-TOW-009, REQ-TOW-011, REQ-TOW-012

import json

from src.tower.messaging.db import init_db as init_messages_db, save_message, get_messages
from src.tower.airport.airport_repo import (
    InvalidRunwayTransition, assign_runway, free_runway, get_assigned_runway, mark_processed, is_processed,
    set_assignment_status,
)

REQUEST_LANDING = "REQUEST_LANDING"
REQUEST_TAKEOFF = "REQUEST_TAKEOFF"
LANDED          = "LANDED"
DEPARTED        = "DEPARTED"
PARKED          = "PARKED"           # radar -> tower: the plane has parked, so it's off its runway
RUNWAY_ASSIGNED = "RUNWAY_ASSIGNED"
NO_RUNWAY       = "NO_RUNWAY"
REQUEST_REFUSED = "REQUEST_REFUSED"  # tower -> radar: the request doesn't fit the plane's phase (REQ-TOW-011)
FREED           = "FREED"

# REQ-TOW-009: plane positions, radar -> tower -> command.
AIRCRAFT_INFO     = "AIRCRAFT_INFO"      # radar -> tower (radar's create message is the same data, with no type)
AIRCRAFT_POSITION = "AIRCRAFT_POSITION"  # tower -> command: a plane's latest position
AIRCRAFT_REMOVED  = "AIRCRAFT_REMOVED"   # tower -> command: the plane departed (its runway is already freed)
AIRCRAFT_PARKED   = "AIRCRAFT_PARKED"    # tower -> command: the plane parked (its runway is already freed)
AIRCRAFT_LANDED   = "AIRCRAFT_LANDED"    # tower -> command: the plane landed (still on its runway)
POSITION_FIELDS   = ("aircraft_id", "latitude", "longitude", "altitude", "status", "timestamp")

# Radar's lifecycle events and what tower tells command, once tower has handled them.
FORWARDED_EVENTS  = {LANDED: AIRCRAFT_LANDED, PARKED: AIRCRAFT_PARKED, DEPARTED: AIRCRAFT_REMOVED}

# The phase stored in runway_assignments (command shows it on the runway).
LANDING_ASSIGNED  = "LANDING_ASSIGNED"
LANDED_PHASE      = "LANDED"
TAKEOFF_ASSIGNED  = "TAKEOFF_ASSIGNED"

# Runway messages: only each plane's newest one is answered (see newest_per_plane).
# Position updates are NOT in here, so an update can never hide a runway request that's waiting.
RADAR_MESSAGES = (REQUEST_LANDING, REQUEST_TAKEOFF, LANDED, PARKED, DEPARTED)


def read_tower_inbox():
    init_messages_db()
    return get_messages("tower")


def send_to_radar(content):
    init_messages_db()
    save_message("tower", "radar", content)


def send_to_command(content):
    init_messages_db()
    save_message("tower", "command", content)


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
    """The plane is down but still on its runway: keep the runway, record it as LANDED. No reply to radar."""
    set_assignment_status(conn, airport_id, aircraft_id, LANDED_PHASE)
    return None


def process_departed(conn, airport_id, aircraft_id, request):
    runway_id = free_runway(conn, airport_id, aircraft_id)
    if runway_id is not None:
        return {"type": FREED, "aircraft_id": aircraft_id, "runway_id": runway_id}
    return None


def process_parked(conn, airport_id, aircraft_id, request):
    """A parked plane has left its runway, so free it (it stays at the airport, unlike DEPARTED)."""
    runway_id = free_runway(conn, airport_id, aircraft_id)
    if runway_id is not None:
        return {"type": FREED, "aircraft_id": aircraft_id, "runway_id": runway_id, "reason": PARKED}
    return None


def process_clearance(conn, airport_id, aircraft_id, request):
    req_type = request["type"]
    phase = TAKEOFF_ASSIGNED if req_type == REQUEST_TAKEOFF else LANDING_ASSIGNED
    try:
        runway_id = assign_runway(conn, airport_id, aircraft_id, phase)
    except InvalidRunwayTransition as refused:
        # e.g. REQUEST_TAKEOFF while still LANDING_ASSIGNED (it hasn't landed). Nothing changes; radar is told why,
        # and the message is still marked handled, so it can't stop tower answering everyone else.
        reply = {"type": REQUEST_REFUSED, "aircraft_id": aircraft_id, "phase": refused.current_status,
                 "reason": f"{aircraft_id} is {refused.current_status}, so it can't get {phase}"}
        reply["request"] = req_type
        reply["request_timestamp"] = request.get("timestamp")
        return reply

    if runway_id is None:
        reply = {"type": NO_RUNWAY, "aircraft_id": aircraft_id}
    else:
        reply = {"type": RUNWAY_ASSIGNED, "aircraft_id": aircraft_id, "runway_id": runway_id}

    reply["request"] = req_type
    reply["request_timestamp"] = request.get("timestamp")
    return reply


HANDLERS = {
    LANDED:          process_landed,
    PARKED:          process_parked,
    DEPARTED:        process_departed,
    REQUEST_LANDING: process_clearance,
    REQUEST_TAKEOFF: process_clearance,
}


def answer_requests(conn, airport_id, get=read_tower_inbox, send=send_to_radar, tell_command=send_to_command):
    """Answer each plane's newest runway message. Replies go to radar; a NO_RUNWAY also goes to command
    (REQ-TOW-012), so it can show the plane is waiting. `get`, `send` and `tell_command` are for tests.
    """
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
            if result.get("type") == NO_RUNWAY:
                tell_command(json.dumps(result))  # the same reply radar got
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


# --- REQ-TOW-009: radar -> tower -> command plane positions ---

def read_position(message):
    """Radar's plane data as a dict, or None.

    That's radar's create message (no "type") or an AIRCRAFT_INFO update; both have a position.
    """
    if message.get("sender") != "radar":
        return None
    data = read_json(message)
    if data is None or not isinstance(data.get("aircraft_id"), str):
        return None
    if data.get("type", AIRCRAFT_INFO) != AIRCRAFT_INFO:
        return None  # a runway request, LANDED, or DEPARTED
    if "latitude" not in data or "longitude" not in data:
        return None
    return data


def forward_positions(conn, airport_id, get=read_tower_inbox, send=send_to_command):
    """Send command every new plane position from radar, and tell it when a plane lands, parks, or departs.

    LANDED, PARKED, and DEPARTED are only passed on once answer_requests has handled them (recorded the
    landing / freed the runway), so command never hears about them before tower has acted.
    Until then they wait for a later run.
    Messages are handled in the order radar sent them, each one once, so command can keep the newest
    message per plane. Returns what was sent, as dicts.
    `get` and `send` are only there so tests can swap in fakes.
    """
    sent = []
    for message in get():
        position = read_position(message)
        request = read_request(message)
        if position is not None:
            aircraft_id = position["aircraft_id"]
            out = {"type": AIRCRAFT_POSITION, **{field: position.get(field) for field in POSITION_FIELDS},
                   "runway_id": get_assigned_runway(conn, airport_id, aircraft_id)}  # tower's runway, not radar's
            # Timestamps are to the second, so include the data: a real change is new, an exact repeat isn't.
            key = f"{aircraft_id}:{AIRCRAFT_POSITION}:" + json.dumps(position, sort_keys=True)
        elif request is not None and request["type"] in FORWARDED_EVENTS:
            aircraft_id, timestamp = request["aircraft_id"], request.get("timestamp")
            if not is_processed(conn, f"{aircraft_id}:{request['type']}:{timestamp}"):
                continue  # answer_requests hasn't handled it yet; send it on a later run
            out_type = FORWARDED_EVENTS[request["type"]]
            out = {"type": out_type, "aircraft_id": aircraft_id, "timestamp": timestamp}
            key = f"{aircraft_id}:{out_type}:{timestamp}"
        else:
            continue
        if is_processed(conn, key):
            continue  # already sent to command
        send(json.dumps(out))
        mark_processed(conn, key)
        sent.append(out)
    return sent
