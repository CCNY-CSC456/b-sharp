# REQ-TOW-008
# runway_requests.py — tower reads radar's runway requests and answers them.
#
# radar -> tower:  "AA123 wants to land" / "AA123 wants to take off"
# tower -> radar:  "AA123 gets runway 1" / "no runway for AA123"
#
# Every message is JSON text in the message's content, sent with tower's messaging service.
# The message format is radar's (REQ-RAD-013), so these names must match radar's exactly.
# Nothing happens in the background: requests are only answered when answer_requests() is called.

import json

from src.tower.messaging.db import init_db as init_messages_db, save_message, get_messages
from src.tower.airport.airport_repo import assign_runway

REQUEST_LANDING = "REQUEST_LANDING"    # radar -> tower
REQUEST_TAKEOFF = "REQUEST_TAKEOFF"    # radar -> tower
RUNWAY_ASSIGNED = "RUNWAY_ASSIGNED"    # tower -> radar, includes "runway_id"
NO_RUNWAY       = "NO_RUNWAY"                # tower -> radar


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
    """Turn one inbox message into a request dict, or None if it isn't a runway request from radar."""
    if message["sender"] != "radar":
        return None
    request = read_json(message)
    if request is None or not isinstance(request.get("aircraft_id"), str):
        return None
    if request.get("type") not in (REQUEST_LANDING, REQUEST_TAKEOFF):
        return None  # e.g. the airplane data radar sends when it creates a plane
    return request


def answer_requests(conn, airport_id, get=read_tower_inbox, sent_to_radar=read_radar_inbox, send=send_to_radar):
    """Answer every runway request in tower's inbox. Returns the replies that were sent, as dicts.

    The inbox holds EVERY request ever sent, so the same requests come back each time this runs.
    assign_runway() gives a plane the same runway again, and a reply is skipped if tower already
    sent radar that exact answer, so running this twice in a row sends nothing the second time.
    `get`, `sent_to_radar`, and `send` are only there so tests can swap in fakes.
    """
    # Messages come back oldest first. One answer per plane is enough.
    planes = []
    for message in get():
        request = read_request(message)
        if request is not None and request["aircraft_id"] not in planes:
            planes.append(request["aircraft_id"])

    # The last answer tower gave each plane, read from radar's inbox.
    last_answer = {}
    for message in sent_to_radar():
        reply = read_json(message) if message["sender"] == "tower" else None
        if reply is not None and "aircraft_id" in reply:
            last_answer[reply["aircraft_id"]] = reply

    replies = []
    for aircraft_id in planes:
        runway_id = assign_runway(conn, airport_id, aircraft_id)
        if runway_id is None:
            reply = {"type": NO_RUNWAY, "aircraft_id": aircraft_id}
        else:
            reply = {"type": RUNWAY_ASSIGNED, "aircraft_id": aircraft_id, "runway_id": runway_id}
        if last_answer.get(aircraft_id) == reply:
            continue  # radar already has this answer
        send(json.dumps(reply))  # dict -> JSON text, because message content is text
        replies.append(reply)
    return replies
