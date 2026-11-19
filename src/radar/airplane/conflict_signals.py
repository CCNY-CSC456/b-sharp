# REQ-RAD-017 / REQ-RAD-018
# conflict_signals.py handles R2 unsafe separation replies from tower and continuous conflict signals.
#
# tower -> radar:  UNSAFE_SEPARATION (with separation_id, move_to_latitude, move_to_longitude)
# radar -> tower:  UNSAFE_SEPARATION_RESOLVED (with separation_id, aircraft_id)
# radar -> tower:  CONFLICT every 1 second until tower sends CONFLICT_RESOLVED

import json
import time

from src.radar.airplane.aircraft_repo import TIME_FORMAT, get_aircraft, now, update_position
from src.radar.airplane.runway_requests import (
    read_radar_inbox, send_aircraft_info, send_as_tower, send_to_tower,
)

UNSAFE_SEPARATION = "UNSAFE_SEPARATION"                    # tower -> radar
UNSAFE_SEPARATION_RESOLVED = "UNSAFE_SEPARATION_RESOLVED"  # radar -> tower
CONFLICT = "CONFLICT"                                      # radar -> tower (sent every 1s)
CONFLICT_RESOLVED = "CONFLICT_RESOLVED"                    # tower -> radar

CONFLICT_REASONS = ("Late by +2 hour", "Late by +4 hour", "Low on Gas")

def read_unsafe_separation(message):
    """Turn one UNSAFE_SEPARATION inbox message into a dict, or None if radar should ignore it."""
    if message.get("sender") != "tower":
        return None
    try:
        data = json.loads(message["content"])
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("type") != UNSAFE_SEPARATION:
        return None

    separation_id = data.get("separation_id")
    aircraft_id = data.get("aircraft_id")
    lat = data.get("move_to_latitude")
    lon = data.get("move_to_longitude")

    if isinstance(separation_id, bool) or not isinstance(separation_id, int):
        return None
    if not isinstance(aircraft_id, str):
        return None
    if isinstance(lat, bool) or not isinstance(lat, (int, float)):
        return None
    if isinstance(lon, bool) or not isinstance(lon, (int, float)):
        return None
    return data

def check_unsafe_separation(conn, get=read_radar_inbox, send=send_to_tower):
    """Read UNSAFE_SEPARATION messages from tower, move the plane, reply UNSAFE_SEPARATION_RESOLVED.

    Because the inbox remembers everything, we need to make sure that we're only looking at the new ones.
    """
    messages = get()

    # Find which separation_ids radar has already answered so running this twice is safe
    already_resolved = set()
    for message in messages:
        if message.get("sender") != "radar":
            continue
        try:
            data = json.loads(message["content"])
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("type") == UNSAFE_SEPARATION_RESOLVED:
            sep_id = data.get("separation_id")
            if isinstance(sep_id, int) and not isinstance(sep_id, bool):
                already_resolved.add(sep_id)

    # Keep the newest instruction per separation_id
    pending = {}
    for message in messages:
        instruction = read_unsafe_separation(message)
        if instruction is not None and instruction["separation_id"] not in already_resolved:
            pending[instruction["separation_id"]] = instruction

    results = []
    for separation_id, instruction in pending.items():
        aircraft_id = instruction["aircraft_id"]
        plane = get_aircraft(conn, aircraft_id)
        if plane is None:
            continue

        new_lat = float(instruction["move_to_latitude"])
        new_lon = float(instruction["move_to_longitude"])
        update_position(conn, aircraft_id, new_lat, new_lon)

        reply = {
            "type": UNSAFE_SEPARATION_RESOLVED,
            "separation_id": separation_id,
            "aircraft_id": aircraft_id,
            "timestamp": now().strftime(TIME_FORMAT),
        }
        send(json.dumps(reply))
        send_aircraft_info(conn, aircraft_id, send=send)
        results.append(f"{aircraft_id}: moved to ({new_lat}, {new_lon}) for separation {separation_id}")

    return results

def has_conflict_resolved(aircraft_id, get=read_radar_inbox):
    """True if tower has sent a CONFLICT_RESOLVED message for this aircraft."""
    for message in get():
        if message.get("sender") != "tower":
            continue
        try:
            data = json.loads(message["content"])
        except ValueError:
            continue
        if (
            isinstance(data, dict)
            and data.get("type") == CONFLICT_RESOLVED
            and data.get("aircraft_id") == aircraft_id
        ):
            return True
    return False

def send_conflict_until_resolved(
    conn,
    aircraft_id,
    reason,
    send=send_to_tower,
    get=read_radar_inbox,
    interval_seconds=1.0,
    max_attempts=60,
):
    """Send a CONFLICT message to tower every 1 second until tower replies CONFLICT_RESOLVED.

    Returns True when resolved, or False if max_attempts is reached first.
    """
    plane = get_aircraft(conn, aircraft_id)
    if plane is None:
        raise ValueError(f"aircraft {aircraft_id} does not exist")
    if reason not in CONFLICT_REASONS:
        raise ValueError(f"invalid conflict reason: {reason}")

    attempts = 0
    while attempts < max_attempts:
        if not has_conflict_resolved(aircraft_id, get=get):
            message = {
                "type": CONFLICT,
                "aircraft_id": aircraft_id,
                "reason": reason,
                "timestamp": now().strftime(TIME_FORMAT),
            }
            send(json.dumps(message))
            attempts += 1

        if has_conflict_resolved(aircraft_id, get=get):
            update_position(conn, aircraft_id, plane.latitude, plane.longitude)
            send_aircraft_info(conn, aircraft_id, send=send)
            return True

        if attempts < max_attempts and interval_seconds > 0:
            time.sleep(interval_seconds)

    return False

def fake_conflict_resolved(aircraft_id, send=send_as_tower):
    """TESTING ONLY: send radar a CONFLICT_RESOLVED reply as if tower sent it."""
    reply = {"type": CONFLICT_RESOLVED, "aircraft_id": aircraft_id, "timestamp": now().strftime(TIME_FORMAT)}
    send(json.dumps(reply))
    return reply