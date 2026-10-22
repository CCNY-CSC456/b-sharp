# REQ-TOW-008, REQ-TOW-011
# runway_requests.py — tower reads radar's runway messages and answers them.
#
# radar -> tower:  "AA123 wants to land" / "AA123 wants to take off"
#                  "AA123 has landed" (still on its runway) / "AA123 has departed" (runway is free)
# tower -> radar:  "AA123 gets runway 1" / "no runway for AA123"
#
# Every message is JSON text in the message's content, sent with tower's messaging service.
# The message format is radar's (REQ-RAD-013, REQ-RAD-014), so these names must match radar's exactly.
# Nothing happens in the background: messages are only handled when answer_requests() is called.

import json

from src.tower.messaging.db import init_db as init_messages_db, save_message, get_messages
from src.tower.airport.airport_repo import assign_runway, free_runway

REQUEST_LANDING = "REQUEST_LANDING"    # radar -> tower
REQUEST_TAKEOFF = "REQUEST_TAKEOFF"    # radar -> tower
LANDED = "LANDED"                      # radar -> tower, plane is down but still on its runway
DEPARTED = "DEPARTED"                  # radar -> tower, plane left the ground through its runway
RUNWAY_ASSIGNED = "RUNWAY_ASSIGNED"    # tower -> radar, includes "runway_id"
NO_RUNWAY       = "NO_RUNWAY"                # tower -> radar

# Not a message: answer_requests() reports this when a DEPARTED frees a runway. Radar isn't told.
FREED = "FREED"

REQUESTS = (REQUEST_LANDING, REQUEST_TAKEOFF)
RADAR_MESSAGES = (REQUEST_LANDING, REQUEST_TAKEOFF, LANDED, DEPARTED)


def read_tower_inbox():
    """Every message ever sent to tower (the messaging has no "already read" flag)."""
    init_messages_db()  # makes sure the messages table exists (safe to call every time)
    return get_messages("tower")


def read_radar_inbox():
    """Every message ever sent to radar. Tower checks it so it doesn't repeat itself."""
    init_messages_db()
    return get_messages("radar")


def send_to_radar(content):
    """Put one message in radar's inbox. Run from the repo root so it uses the shared messages.db."""
    init_messages_db()
    save_message("tower", "radar", content)


def read_json(message):
    """The message's content as a dict, or None if it isn't a JSON object (e.g. plain text)."""
    try:
        content = json.loads(message["content"])  # JSON text -> dict
    except ValueError:
        return None
    return content if isinstance(content, dict) else None


def read_request(message):
    """Turn one inbox message into a dict, or None if it isn't one of radar's runway messages.

    Runway messages are the two requests plus LANDED and DEPARTED.
    """
    if message["sender"] != "radar":
        return None
    request = read_json(message)
    if request is None or not isinstance(request.get("aircraft_id"), str):
        return None
    if request.get("type") not in RADAR_MESSAGES:
        return None  # e.g. the airplane data radar sends when it creates a plane
    return request


def answer_requests(conn, airport_id, get=read_tower_inbox, sent_to_radar=read_radar_inbox, send=send_to_radar):
    """Handle radar's runway messages. Returns what happened, as dicts.

    Only each plane's NEWEST message counts, because the inbox holds every message ever sent:
      REQUEST_LANDING / REQUEST_TAKEOFF -> assign a runway (or the one it already holds) and reply
      LANDED                            -> nothing: the plane is still on its runway
      DEPARTED                          -> free its runway; reported as FREED, radar isn't told
    Each reply says which request it answers, so a new request (like a takeoff after landing) is
    always answered, and a reply radar already has is never sent again. Running this twice in a row
    changes nothing the second time.
    `get`, `sent_to_radar`, and `send` are only there so tests can swap in fakes.
    """
    last_answer = last_answers(sent_to_radar())
    results = []
    for aircraft_id, message in newest_per_plane(get()).items():
        if message["type"] == LANDED:
            continue  # still on its runway
        if message["type"] == DEPARTED:
            runway_id = free_runway(conn, airport_id, aircraft_id)
            if runway_id is not None:  # None = already freed, or it never had one
                results.append({"type": FREED, "aircraft_id": aircraft_id, "runway_id": runway_id})
            continue
        reply = reply_to(conn, airport_id, message)
        if last_answer.get(aircraft_id) == reply:
            continue  # radar already has this answer
        send(json.dumps(reply))  # dict -> JSON text, because message content is text
        results.append(reply)
    return results


def newest_per_plane(inbox):
    """Each plane's newest runway message. Messages come back oldest first, so later ones replace earlier ones."""
    newest = {}
    for message in inbox:
        request = read_request(message)
        if request is not None:
            newest[request["aircraft_id"]] = request
    return newest


def last_answers(radar_inbox):
    """The last reply tower sent each plane, read from radar's inbox."""
    last = {}
    for message in radar_inbox:
        reply = read_json(message) if message["sender"] == "tower" else None
        if reply is not None and "aircraft_id" in reply:
            last[reply["aircraft_id"]] = reply
    return last


def reply_to(conn, airport_id, request):
    """Assign a runway for a landing or takeoff request and build tower's reply."""
    aircraft_id = request["aircraft_id"]
    runway_id = assign_runway(conn, airport_id, aircraft_id)  # the same runway if it already has one
    if runway_id is None:
        reply = {"type": NO_RUNWAY, "aircraft_id": aircraft_id}
    else:
        reply = {"type": RUNWAY_ASSIGNED, "aircraft_id": aircraft_id, "runway_id": runway_id}
    # Which request this answers. A takeoff after landing gets the same runway, but it's a new
    # request, so it's a new reply: that reply is the plane's clearance for takeoff.
    reply["request"] = request["type"]
    reply["request_timestamp"] = request.get("timestamp")
    return reply
