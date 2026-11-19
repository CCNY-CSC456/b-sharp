# REQ-RAD-017
# separation.py — do what tower says when two planes are too close.
#
# tower -> radar:  UNSAFE_SEPARATION           {separation_id, aircraft_id, other_aircraft_id,
#                                               move_to_latitude, move_to_longitude, timestamp}  (REQ-TOW-013)
# radar -> tower:  UNSAFE_SEPARATION_RESOLVED  {separation_id, aircraft_id, timestamp}
#                  then AIRCRAFT_INFO with the plane's new position (REQ-RAD-016)
#
# Each event is handled once. Radar's inbox returns every message ever sent, so radar remembers
# which events it has answered (handled_messages in radar.db).

import json

from src.radar.airplane.aircraft_repo import (
    TIME_FORMAT, get_aircraft, is_handled, mark_handled, now, update_position,
)
from src.radar.airplane.runway_requests import send_aircraft_info, send_as_tower, send_to_tower
from src.radar.airplane.tower_inbox import as_coordinate, from_tower, is_int

UNSAFE_SEPARATION = "UNSAFE_SEPARATION"                    # tower -> radar
UNSAFE_SEPARATION_RESOLVED = "UNSAFE_SEPARATION_RESOLVED"  # radar -> tower


def read_move(data):
    """(separation_id, aircraft_id, latitude, longitude, key) from one UNSAFE_SEPARATION, or None if it's bad."""
    separation_id, aircraft_id = data.get("separation_id"), data.get("aircraft_id")
    latitude = as_coordinate(data.get("move_to_latitude"), 90)
    longitude = as_coordinate(data.get("move_to_longitude"), 180)
    if not is_int(separation_id) or not isinstance(aircraft_id, str) or None in (latitude, longitude):
        return None
    # The timestamp is part of the key: if tower.db is reset, separation_id starts at 1 again.
    key = f"{UNSAFE_SEPARATION}:{separation_id}:{aircraft_id}:{data.get('timestamp')}"
    return separation_id, aircraft_id, latitude, longitude, key


def handle_unsafe_separation(conn, inbox, send=send_to_tower, clock=now):
    """Move every plane tower asked to move, and tell tower it's done. Returns what happened, as text."""
    results = []
    for data in from_tower(inbox, UNSAFE_SEPARATION):
        move = read_move(data)
        if move is None:
            continue
        separation_id, aircraft_id, latitude, longitude, key = move
        if is_handled(conn, key) or get_aircraft(conn, aircraft_id) is None:
            continue
        update_position(conn, aircraft_id, latitude, longitude, clock=clock)
        send(json.dumps({"type": UNSAFE_SEPARATION_RESOLVED, "separation_id": separation_id,
                         "aircraft_id": aircraft_id, "timestamp": clock().strftime(TIME_FORMAT)}))
        send_aircraft_info(conn, aircraft_id, send=send)
        mark_handled(conn, key)
        results.append(f"{aircraft_id}: moved to ({latitude}, {longitude}) for unsafe separation {separation_id}")
    return results


def fake_unsafe_separation(aircraft_id, latitude, longitude, send=send_as_tower, clock=now):
    """TESTING ONLY: send radar an UNSAFE_SEPARATION as if tower sent it. Returns the message, as a dict."""
    stamp = clock()
    message = {"type": UNSAFE_SEPARATION, "separation_id": int(stamp.timestamp()), "aircraft_id": aircraft_id,
               "other_aircraft_id": None, "move_to_latitude": latitude, "move_to_longitude": longitude,
               "timestamp": stamp.strftime(TIME_FORMAT)}
    send(json.dumps(message))
    return message
