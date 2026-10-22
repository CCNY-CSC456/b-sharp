# REQ-RAD-013
# runway_requests.py — radar asks tower for a runway and reads tower's answers.
#
# radar -> tower:  "AA123 wants to land" / "AA123 wants to take off"
# tower -> radar:  "AA123 gets runway R1" / "no runway for AA123"
#
# Every message is JSON text in the message's content, sent with tower's messaging service.
# Nothing happens in the background: replies are only read when check_tower_replies() is called.

import json

# Tower's messaging functions, used exactly as tower wrote them.
from src.tower.messaging.db import init_db as init_messages_db, save_message, get_messages

from src.radar.airplane.aircraft_repo import TIME_FORMAT, delete_aircraft, get_aircraft, now, update_runway

# The message types, all in one place. If tower wants different names, change them here.
REQUEST_LANDING = "REQUEST_LANDING"    # radar -> tower
REQUEST_TAKEOFF = "REQUEST_TAKEOFF"    # radar -> tower
RUNWAY_ASSIGNED = "RUNWAY_ASSIGNED"    # tower -> radar, includes "runway_id"
NO_RUNWAY = "NO_RUNWAY"                # tower -> radar
LANDED = "LANDED"                      # radar -> tower, plane is off the runway (REQ-RAD-014)
DEPARTED = "DEPARTED"                  # radar -> tower, plane has left (REQ-RAD-014)


def send_to_tower(content):
    """Put one message in tower's inbox. Run from the repo root so it uses the shared messages.db."""
    init_messages_db()  # makes sure the messages table exists (safe to call every time)
    save_message("radar", "tower", content)


def read_radar_inbox():
    """Every message ever sent to radar (tower's messaging has no "already read" flag)."""
    init_messages_db()
    return get_messages("radar")


# --- radar -> tower ---

def request_runway(conn, aircraft_id, request_type, send):
    """Ask tower for a runway. Raises ValueError if radar has no plane with this ID.

    Returns the message that was sent, as a dict.
    """
    if get_aircraft(conn, aircraft_id) is None:
        raise ValueError(f"aircraft {aircraft_id} does not exist")
    message = {
        "type": request_type,
        "aircraft_id": aircraft_id,
        "timestamp": now().strftime(TIME_FORMAT),
    }
    send(json.dumps(message))  # dict -> JSON text, because message content is text
    return message


# `send` is only there so tests can swap in a fake instead of the real messaging service.
def request_landing(conn, aircraft_id, send=send_to_tower):
    return request_runway(conn, aircraft_id, REQUEST_LANDING, send)


def request_takeoff(conn, aircraft_id, send=send_to_tower):
    return request_runway(conn, aircraft_id, REQUEST_TAKEOFF, send)



# --- radar -> tower: done with the runway (REQ-RAD-014) ---

def report_landed(conn, aircraft_id, send=send_to_tower):
    """Tell tower the plane has landed, so tower can free its runway. The plane is not changed."""
    return request_runway(conn, aircraft_id, LANDED, send)


def report_departed(conn, aircraft_id, send=send_to_tower):
    """Tell tower the plane has departed, then remove it from radar.

    The message is sent FIRST: if sending fails, the plane is kept so this can be retried.
    """
    message = request_runway(conn, aircraft_id, DEPARTED, send)
    # Delete the plane, because check_tower_replies re-reads old replies every time and
    # would put the runway back on a plane that still exists.
    delete_aircraft(conn, aircraft_id)
    return message

# --- tower -> radar ---

def read_reply(message):
    """Turn one inbox message into a reply dict, or None if radar should ignore it."""
    if message["sender"] != "tower":
        return None
    try:
        reply = json.loads(message["content"])  # JSON text -> dict
    except ValueError:  # not JSON, e.g. a normal text message
        return None
    if not isinstance(reply, dict) or not isinstance(reply.get("aircraft_id"), str):
        return None
    if reply.get("type") == NO_RUNWAY:
        return reply
    if reply.get("type") == RUNWAY_ASSIGNED and reply.get("runway_id") is not None:
        return reply
    return None  # unknown type, or a RUNWAY_ASSIGNED without a runway


def check_tower_replies(conn, get=read_radar_inbox):
    """Read tower's replies and update the planes. Returns a list of what happened, as text.

    The inbox holds EVERY reply ever sent, so the same replies come back each time this runs.
    That's why only the newest reply for each plane counts, and a runway that is already set
    isn't written again. Running this twice in a row changes nothing the second time.
    `get` is only there so tests can swap in fake replies.
    """
    # Messages come back oldest first, so a later reply for the same plane replaces an earlier one.
    latest = {}
    for message in get():
        reply = read_reply(message)
        if reply is not None:
            latest[reply["aircraft_id"]] = reply

    results = []
    for aircraft_id, reply in latest.items():
        plane = get_aircraft(conn, aircraft_id)
        if plane is None:  # tower named a plane radar doesn't have
            continue
        if reply["type"] == NO_RUNWAY:
            # Leave the plane's runway as it is and just report it.
            results.append(f"{aircraft_id}: no runway available")
            continue
        runway_id = str(reply["runway_id"])  # tower may send "R1" or 3; keep it as text either way
        if plane.runway_id == runway_id:
            results.append(f"{aircraft_id}: already on runway {runway_id}")
        else:
            update_runway(conn, aircraft_id, runway_id)
            results.append(f"{aircraft_id}: runway {runway_id} assigned")
    return results


# --- testing helper: pretend to be tower ---

def send_as_tower(content):
    """Put one message in radar's inbox, written as if tower sent it."""
    init_messages_db()
    save_message("tower", "radar", content)


def fake_tower_reply(aircraft_id, runway_id, send=send_as_tower):
    """TESTING ONLY: answer radar the way tower will once tower's runway code exists.

    A runway_id gives a RUNWAY_ASSIGNED reply. Empty or None gives a NO_RUNWAY reply.
    Returns the message that was sent, as a dict.
    """
    if runway_id:
        reply = {"type": RUNWAY_ASSIGNED, "aircraft_id": aircraft_id, "runway_id": runway_id}
    else:
        reply = {"type": NO_RUNWAY, "aircraft_id": aircraft_id}
    send(json.dumps(reply))
    return reply
