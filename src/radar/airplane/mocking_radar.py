"""Synthetic tower-message injectors for local testing and fixtures.

Isolated outside __main__.py so CLI subcommands remain real operational commands
rather than exposing test-message injection as user-facing CLI behavior.
"""

### 1
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.radar.airplane.runway_requests import send_to_tower
###

### 2
import json

from src.radar.airplane.aircraft_repo import (
    TIME_FORMAT, get_aircraft, is_handled, mark_handled, now, update_position,
)
from src.radar.airplane.runway_requests import send_aircraft_info, send_as_tower, send_to_tower
from src.radar.airplane.tower_inbox import as_coordinate, from_tower, is_int

UNSAFE_SEPARATION = "UNSAFE_SEPARATION"                    # tower -> radar
UNSAFE_SEPARATION_RESOLVED = "UNSAFE_SEPARATION_RESOLVED"  # radar -> tower
###

### 3
import json

# Tower's messaging functions, used exactly as tower wrote them.
from src.tower.messaging.db import init_db as init_messages_db, save_message, get_messages

from src.radar.airplane.aircraft_repo import TIME_FORMAT, get_aircraft, now, record_departure, update_runway

# The message types, all in one place. If tower wants different names, change them here.
REQUEST_LANDING = "REQUEST_LANDING"    # radar -> tower
REQUEST_TAKEOFF = "REQUEST_TAKEOFF"    # radar -> tower
RUNWAY_ASSIGNED = "RUNWAY_ASSIGNED"    # tower -> radar, includes "runway_id"
NO_RUNWAY = "NO_RUNWAY"                # tower -> radar
LANDED = "LANDED"                      # radar -> tower, plane is off the runway (REQ-RAD-014)
DEPARTED = "DEPARTED"                  # radar -> tower, plane has left (REQ-RAD-014)
PARKED = "PARKED"                      # radar -> tower, landed plane is off its runway (REQ-RAD-019)
AIRCRAFT_INFO = "AIRCRAFT_INFO"        # radar -> tower, a plane's current data (REQ-RAD-016)
###

### 4

from src.radar.airplane.conflicts import (
    #CONFLICT_REASONS,
    fake_conflict_resolved,
    #get_conflict,
    #get_conflicts,
    #open_conflict,
)

from src.radar.airplane.runway_requests import (
    #check_tower_replies,
    fake_tower_reply,
    #report_departed,
    #report_landed,
    #report_parked,
    #request_landing,
    #request_takeoff,
    #send_aircraft_info,
)

from src.radar.airplane.separation import fake_unsafe_separation

###


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def inject_tower_reply(
    aircraft_id: str,
    runway_id: str = "",
    request: str = "REQUEST_LANDING",
    request_timestamp: str | None = None,
) -> dict:
    """Write a synthetic RUNWAY_ASSIGNED or NO_RUNWAY message from tower into radar's inbox."""
    ts = request_timestamp or _now_iso()
    payload = (
        {
            "type": "RUNWAY_ASSIGNED",
            "aircraft_id": aircraft_id,
            "runway_id": runway_id,
            "request": request,
            "request_timestamp": ts,
        }
        if runway_id
        else {
            "type": "NO_RUNWAY",
            "aircraft_id": aircraft_id,
            "request": request,
            "request_timestamp": ts,
        }
    )
    envelope = {
        "sender": "tower",
        "recipient": "radar",
        "content": json.dumps(payload),
    }
    send_to_tower(json.dumps(payload))
    return envelope


def inject_unsafe_separation(
    aircraft_id: str,
    move_to_latitude: float,
    move_to_longitude: float,
    other_aircraft_id: str = "OTHER",
    separation_id: int = 1,
    timestamp: str | None = None,
) -> dict:
    """Write a synthetic UNSAFE_SEPARATION directive from tower into radar's inbox."""
    payload = {
        "type": "UNSAFE_SEPARATION",
        "separation_id": separation_id,
        "aircraft_id": aircraft_id,
        "other_aircraft_id": other_aircraft_id,
        "move_to_latitude": move_to_latitude,
        "move_to_longitude": move_to_longitude,
        "timestamp": timestamp or _now_iso(),
    }
    send_to_tower(json.dumps(payload))
    return payload


def inject_conflict_resolved(
    conflict: dict,
    queue_position: int = 1,
    timestamp: str | None = None,
) -> dict:
    """Write a synthetic CONFLICT_RESOLVED message from tower into radar's inbox."""
    payload = {
        "type": "CONFLICT_RESOLVED",
        "conflict_id": conflict["conflict_id"],
        "aircraft_id": conflict["aircraft_id"],
        "reason": conflict["reason"],
        "queue_position": queue_position,
        "timestamp": timestamp or _now_iso(),
    }
    send_to_tower(json.dumps(payload))
    return payload

# NOTE Pulled out of main, may not be appropriately wired out yet

def cmd_fake_reply(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id
    pos_runway = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_runway_id

    interactive = args.interactive or (
        not json_data
        and args.aircraft_id is None
        and pos_id is None
        and args.runway_id is None
        and pos_runway is None
    )

    aircraft_id = pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text("Aircraft ID"),
        str,
    )
    if get_aircraft(conn, aircraft_id) is None:
        raise ValueError(f"radar has no aircraft {aircraft_id}")

    runway_id = pick_value(
        args.runway_id,
        pos_runway,
        json_data,
        ["runway_id", "runway"],
        interactive,
        lambda: input("Runway (leave empty for no runway): ").strip(),
        lambda v: "" if v is None else str(v).strip(),
        required=False,
    )
    if runway_id is None:
        runway_id = ""

    fake_tower_reply(aircraft_id, runway_id)
    answer = f"runway {runway_id}" if runway_id else "no runway"
    print(f"\nTower replied: {answer} for {aircraft_id} (test reply). Run check-replies to read it.")


def cmd_fake_unsafe_separation(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id
    interactive = args.interactive or (
        not json_data
        and args.aircraft_id is None
        and pos_id is None
        and args.latitude is None
        and args.pos_latitude is None
        and args.longitude is None
        and args.pos_longitude is None
    )

    aircraft_id = pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text("Aircraft ID"),
        str,
    )
    if get_aircraft(conn, aircraft_id) is None:
        raise ValueError(f"radar has no aircraft {aircraft_id}")

    latitude = pick_value(
        args.latitude,
        args.pos_latitude,
        json_data,
        ["latitude", "lat"],
        interactive,
        lambda: ask_number("Move to latitude"),
        float,
    )
    longitude = pick_value(
        args.longitude,
        args.pos_longitude,
        json_data,
        ["longitude", "lon", "lng"],
        interactive,
        lambda: ask_number("Move to longitude"),
        float,
    )

    fake_unsafe_separation(aircraft_id, latitude, longitude)
    print(
        f"\nTower told radar to move {aircraft_id} to ({latitude}, {longitude}) (test message). "
        "Run `run --once` to handle it."
    )


def cmd_fake_conflict_resolved(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_conflict_id, args.json_payload, args.command)
    pos_cid = None if _is_json_or_file_token(args.pos_conflict_id) else args.pos_conflict_id
    interactive = args.interactive or (
        not json_data and args.conflict_id is None and pos_cid is None
    )

    open_conflicts = get_conflicts(conn, "OPEN")
    if interactive and open_conflicts:
        open_ids = [c["conflict_id"] for c in open_conflicts]
        print("Open conflicts: " + ", ".join(open_ids))

    conflict_id = pick_value(
        args.conflict_id,
        pos_cid,
        json_data,
        ["conflict_id", "id"],
        interactive,
        lambda: ask_text("Conflict ID"),
        str,
    )
    conflict = get_conflict(conn, conflict_id)
    if conflict is None or conflict["status"] != "OPEN":
        raise ValueError(f"no open conflict with ID {conflict_id}")

    fake_conflict_resolved(conflict)
    print(
        f"\nTower resolved {conflict['conflict_id']} (test message). "
        "Run `run --once` to handle it."
    )

# NOTE Transplants of things clearly not for prod these may not be adequately
# rewired up yet and thus may need to be commented out

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
#
def fake_unsafe_separation(aircraft_id, latitude, longitude, send=send_as_tower, clock=now):
    """TESTING ONLY: send radar an UNSAFE_SEPARATION as if tower sent it. Returns the message, as a dict."""
    stamp = clock()
    message = {"type": UNSAFE_SEPARATION, "separation_id": int(stamp.timestamp()), "aircraft_id": aircraft_id,
               "other_aircraft_id": None, "move_to_latitude": latitude, "move_to_longitude": longitude,
               "timestamp": stamp.strftime(TIME_FORMAT)}
    send(json.dumps(message))
    return message

# NOTE pulled from original r2 in from chat history

def fake_separation(conn):
  """TESTING ONLY: send radar an UNSAFE_SEPARATION as if tower sent it."""
  aircraft_id = ask_text("Aircraft ID")
  if get_aircraft(conn, aircraft_id) is None:
    print(f"\nNot sent: radar has no aircraft {aircraft_id}")
    return
  latitude = ask_number("Move to latitude")
  longitude = ask_number("Move to longitude")
  fake_unsafe_separation(aircraft_id, latitude, longitude)
  print(f"\nTower told radar to move {aircraft_id} to ({latitude}, {longitude}) (test message). " "Run `run --once` to handle it.")



def fake_resolve(conn):
  """TESTING ONLY: send radar a CONFLICT_RESOLVED as if tower sent it."""
  open_ids = [c["conflict_id"] for c in get_conflicts(conn, "OPEN")]
  if not open_ids:
    print("\nNo open conflicts to resolve.")
    return
  print("Open conflicts: " + ", ".join(open_ids))

  conflict = get_conflict(conn, ask_text("Conflict ID"))
  if conflict is None or conflict["status"] != "OPEN":
    print("\nNot sent: no open conflict with that ID")
    return

  fake_conflict_resolved(conflict)
  print(f"\nTower resolved {conflict['conflict_id']} (test message). Run `run --once` to handle it.")