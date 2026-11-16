# REQ-TOW-013
# separation.py — find airborne planes that are too close, and tell radar exactly where to move one of them.
#
# Every run, tower:
#   1. rebuilds each plane's latest position from radar's messages (aircraft_positions in tower.db),
#   2. closes events radar has answered (UNSAFE_SEPARATION_RESOLVED) — tower trusts radar,
#   3. cancels events where a plane landed, parked, or departed first,
#   4. retries events that had no clear spot yet (WAITING),
#   5. looks for new pairs that are too close, picks which plane moves, and picks ONE spot for it.
# Every event is a row in the separations table, and each message is sent once.

import itertools
import json
import math

from src.tower.airport.airport_repo import (
    close_separation, get_assigned_runway, get_separations, open_separation, save_aircraft_positions,
    set_separation_move_to, now,
)
from src.tower.airport.runway_requests import (
    DEPARTED, LANDED, PARKED, REQUEST_LANDING, REQUEST_TAKEOFF,
    read_json, read_position, read_tower_inbox, send_to_command, send_to_radar,
)

# Two airborne planes are too close when they are closer than ALL THREE of these.
SEPARATION_DEGREES = 0.10   # latitude and longitude (0.10 degrees of latitude is about 11 km)
SEPARATION_FEET    = 1000   # altitude, in feet (what radar sends)

# Where a plane is sent: this far from the plane that stays, just past SEPARATION_DEGREES.
# If nothing is clear at that distance, tower tries twice as far.
MOVE_DEGREES = 0.11
MOVE_RINGS   = (MOVE_DEGREES, 2 * MOVE_DEGREES)
DECIMALS     = 4            # coordinates sent to radar are rounded to this (about 11 m)

# The 8 spots around the plane that stays, tried in this order when two are equally close.
DIRECTIONS = (("N", 1, 0), ("NE", 1, 1), ("E", 0, 1), ("SE", -1, 1),
              ("S", -1, 0), ("SW", -1, -1), ("W", 0, -1), ("NW", 1, -1))

# Messages (see REQ-TOW-013 for their exact fields).
UNSAFE_SEPARATION          = "UNSAFE_SEPARATION"           # tower -> radar and tower -> command
UNSAFE_SEPARATION_RESOLVED = "UNSAFE_SEPARATION_RESOLVED"  # radar -> tower and tower -> command
SEVERITY = 1                                               # command ranks unsafe separation first

# The status column of the separations table.
WAITING, OPEN, RESOLVED, CANCELLED = "WAITING", "OPEN", "RESOLVED", "CANCELLED"
UNFINISHED = (WAITING, OPEN)

PARKED_STATUS = "Parked"    # radar's status for a parked plane


# --- the rules (no database, so they are easy to test) ---

def too_close(a, b):
    """True if planes a and b are closer than the limit in latitude AND longitude AND altitude.

    Exactly at the limit counts as safe. Differences are rounded first so float noise
    (40.8 - 40.7 = 0.0999999...) can't turn "exactly 0.10 apart" into "too close".
    """
    return (round(abs(a["latitude"] - b["latitude"]), 9) < SEPARATION_DEGREES
            and round(abs(a["longitude"] - b["longitude"]), 9) < SEPARATION_DEGREES
            and round(abs(a["altitude"] - b["altitude"]), 9) < SEPARATION_FEET)


def find_spot(mover, other, planes):
    """The one spot to send `mover` to, as (latitude, longitude), or None if nothing is clear.

    Spots are MOVE_RINGS away from `other` (the plane that stays) in 8 directions, so every spot
    is clear of `other`. A spot is thrown out if it is too close to ANY plane in `planes`
    (positions already include moves tower has sent but radar hasn't confirmed). Of the clear
    spots, the one closest to where `mover` is now wins; ties go in DIRECTIONS order.
    The mover keeps its altitude.
    """
    for ring in MOVE_RINGS:
        options = []
        for order, (_name, lat_sign, lon_sign) in enumerate(DIRECTIONS):
            latitude = round(other["latitude"] + lat_sign * ring, DECIMALS)
            longitude = round(other["longitude"] + lon_sign * ring, DECIMALS)
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            spot = {**mover, "latitude": latitude, "longitude": longitude}
            if any(too_close(spot, plane) for aircraft_id, plane in planes.items()
                   if aircraft_id != mover["aircraft_id"]):
                continue
            distance = round((latitude - mover["latitude"]) ** 2 + (longitude - mover["longitude"]) ** 2, 12)
            options.append((distance, order, latitude, longitude))
        if options:
            _distance, _order, latitude, longitude = min(options)
            return latitude, longitude
    return None


def queue_rank(plane):
    """Bigger = later in the queue. Never asked for a runway is later than asked; ties go by aircraft_id."""
    asked = plane["requested_at"] is not None
    return (not asked, plane["requested_at"] or "", plane["aircraft_id"])


def choose_mover(a, b, busy, holds_runway):
    """Which of the two planes moves, or None if both are already being moved.

    `busy` = planes already told to move (or waiting for a spot); they are not picked again.
    A plane holding a runway is not picked if the other one doesn't hold one.
    Otherwise the plane later in the queue moves (see queue_rank).
    """
    choices = [p for p in (a, b) if p["aircraft_id"] not in busy]
    if len(choices) < 2:
        return choices[0] if choices else None
    if holds_runway(a["aircraft_id"]) != holds_runway(b["aircraft_id"]):
        return b if holds_runway(a["aircraft_id"]) else a
    return max(choices, key=queue_rank)


# --- reading radar's messages ---

def as_number(value):
    """A finite float, or None (bools, text, NaN and infinity are not positions)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def read_resolution(message):
    """Radar's UNSAFE_SEPARATION_RESOLVED as (separation_id, aircraft_id), or None."""
    if message.get("sender") != "radar":
        return None
    data = read_json(message)
    if data is None or data.get("type") != UNSAFE_SEPARATION_RESOLVED:
        return None
    separation_id, aircraft_id = data.get("separation_id"), data.get("aircraft_id")
    if isinstance(separation_id, bool) or not isinstance(separation_id, int) or not isinstance(aircraft_id, str):
        return None
    return separation_id, aircraft_id


def build_positions(inbox, moves):
    """Each plane's latest known position, from radar's messages in the order radar sent them.

    `moves` = {separation_id: (aircraft_id, latitude, longitude)} for events that have a spot.
    - A position (create message or AIRCRAFT_INFO) replaces the plane's last one.
    - UNSAFE_SEPARATION_RESOLVED puts the plane at the spot tower sent (tower trusts radar)
      until radar sends a newer position.
    - LANDED or PARKED marks the plane on the ground until it departs (radar doesn't zero the
      altitude when a plane lands). Altitude 0 or status Parked also means on the ground.
    - DEPARTED removes the plane.
    - REQUEST_LANDING / REQUEST_TAKEOFF record when the plane last asked for a runway.
    Returns a list of dicts (the aircraft_positions columns), sorted by aircraft_id.
    """
    planes, requested_at, landed = {}, {}, set()
    for message in inbox:
        position = read_position(message)
        if position is not None:
            latitude, longitude = as_number(position.get("latitude")), as_number(position.get("longitude"))
            altitude = as_number(position.get("altitude"))
            if None in (latitude, longitude, altitude):
                continue  # can't judge separation without all three; keep the last good position
            aircraft_id = position["aircraft_id"]
            planes[aircraft_id] = {"aircraft_id": aircraft_id, "latitude": latitude, "longitude": longitude,
                                   "altitude": altitude, "status": position.get("status"),
                                   "timestamp": position.get("timestamp")}
            continue
        resolution = read_resolution(message)
        if resolution is not None:
            separation_id, aircraft_id = resolution
            move = moves.get(separation_id)
            if move is not None and move[0] == aircraft_id and aircraft_id in planes:
                planes[aircraft_id].update(latitude=move[1], longitude=move[2], timestamp=read_json(message).get("timestamp"))
            continue
        data = read_json(message) if message.get("sender") == "radar" else None
        if data is None or not isinstance(data.get("aircraft_id"), str):
            continue
        aircraft_id, kind = data["aircraft_id"], data.get("type")
        if kind in (REQUEST_LANDING, REQUEST_TAKEOFF):
            requested_at[aircraft_id] = data.get("timestamp")
        elif kind in (LANDED, PARKED):
            landed.add(aircraft_id)
        elif kind == DEPARTED:
            planes.pop(aircraft_id, None)
            requested_at.pop(aircraft_id, None)
            landed.discard(aircraft_id)

    result = []
    for aircraft_id in sorted(planes):
        plane = planes[aircraft_id]
        on_ground = aircraft_id in landed or plane["altitude"] <= 0 or plane["status"] == PARKED_STATUS
        result.append({**plane, "on_ground": on_ground, "requested_at": requested_at.get(aircraft_id)})
    return result


# --- messages ---

def move_message(event):
    """What radar gets (command gets the same plus severity)."""
    return {"type": UNSAFE_SEPARATION, "separation_id": event["separation_id"], "aircraft_id": event["aircraft_id"],
            "other_aircraft_id": event["other_aircraft_id"], "move_to_latitude": event["move_to_latitude"],
            "move_to_longitude": event["move_to_longitude"], "timestamp": now()}


def with_severity(message):
    """Command's copy of a message: the same fields, with severity right after separation_id."""
    rest = {key: value for key, value in message.items() if key not in ("type", "separation_id")}
    return {"type": message["type"], "separation_id": message["separation_id"], "severity": SEVERITY, **rest}


def resolved_message(event):
    """What command gets when an event is over (radar answered, or a plane left the air)."""
    return with_severity({"type": UNSAFE_SEPARATION_RESOLVED, "separation_id": event["separation_id"],
                          "aircraft_id": event["aircraft_id"], "other_aircraft_id": event["other_aircraft_id"],
                          "timestamp": now()})


# --- one run ---

def check_separation(conn, airport_id, get=read_tower_inbox, to_radar=send_to_radar, to_command=send_to_command):
    """Do one separation pass. Returns the events that changed this run (dicts, in the order they changed).

    `get`, `to_radar` and `to_command` are only there so tests can swap in fakes.
    """
    run = SeparationPass(conn, airport_id, get(), to_radar, to_command)
    run.close_resolved()
    run.cancel_if_a_plane_left_the_air()
    run.place_planes()
    run.retry_waiting()
    run.flag_new_pairs()
    return run.changed


class SeparationPass:
    """One run of the steps at the top of this file. Each step is one method, called in order."""

    def __init__(self, conn, airport_id, inbox, to_radar, to_command):
        self.conn, self.airport_id, self.inbox = conn, airport_id, inbox
        self.to_radar, self.to_command = to_radar, to_command
        self.events = {e["separation_id"]: e for e in get_separations(conn, airport_id)}
        moves = {e["separation_id"]: (e["aircraft_id"], e["move_to_latitude"], e["move_to_longitude"])
                 for e in self.events.values() if e["move_to_latitude"] is not None}
        positions = build_positions(inbox, moves)
        save_aircraft_positions(conn, airport_id, positions)
        self.airborne = {p["aircraft_id"]: p for p in positions if not p["on_ground"]}
        self.planes = {}   # where every airborne plane is, or is about to be (filled by place_planes)
        self.busy = set()  # planes already told to move, or waiting for a spot
        self.changed = []

    def unfinished(self, status=UNFINISHED):
        return [e for e in self.events.values() if e["status"] in status]

    # --- sending ---

    def close(self, event, status):
        if close_separation(self.conn, self.airport_id, event["separation_id"], status):
            event["status"] = status
            self.to_command(json.dumps(resolved_message(event)))
            self.changed.append(dict(event))

    def send_move(self, event):
        message = move_message(event)
        self.to_radar(json.dumps(message))
        self.to_command(json.dumps(with_severity(message)))
        self.planes[event["aircraft_id"]].update(latitude=event["move_to_latitude"],
                                                 longitude=event["move_to_longitude"])

    # --- the steps ---

    def close_resolved(self):
        """Radar says it moved the plane: tower trusts it and closes the event."""
        for message in self.inbox:
            resolution = read_resolution(message)
            if resolution is None:
                continue
            event = self.events.get(resolution[0])
            if event is not None and event["status"] == OPEN and event["aircraft_id"] == resolution[1]:
                self.close(event, RESOLVED)

    def cancel_if_a_plane_left_the_air(self):
        """A plane that landed, parked, or departed ends its unfinished events."""
        for event in self.unfinished():
            if event["aircraft_id"] not in self.airborne or event["other_aircraft_id"] not in self.airborne:
                self.close(event, CANCELLED)

    def place_planes(self):
        """A plane radar was told to move (and hasn't confirmed) counts as already at its spot."""
        self.planes = {aircraft_id: dict(plane) for aircraft_id, plane in self.airborne.items()}
        for event in self.unfinished():
            self.busy.add(event["aircraft_id"])
            if event["status"] == OPEN:
                self.planes[event["aircraft_id"]].update(latitude=event["move_to_latitude"],
                                                         longitude=event["move_to_longitude"])

    def retry_waiting(self):
        """No clear spot last time: over if the planes aren't too close anymore, else look again."""
        for event in self.unfinished((WAITING,)):
            mover, other = self.planes[event["aircraft_id"]], self.planes[event["other_aircraft_id"]]
            if not too_close(mover, other):
                self.close(event, RESOLVED)
                self.busy.discard(event["aircraft_id"])
                continue
            spot = find_spot(mover, other, self.planes)
            if spot is not None:
                set_separation_move_to(self.conn, self.airport_id, event["separation_id"], spot)
                event.update(status=OPEN, move_to_latitude=spot[0], move_to_longitude=spot[1])
                self.send_move(event)
                self.changed.append(dict(event))

    def flag_new_pairs(self):
        """Every pair that is too close and has no event yet gets one (sorted by aircraft_id, so runs repeat)."""
        has_event = {frozenset((e["aircraft_id"], e["other_aircraft_id"])) for e in self.unfinished()}
        for first, second in itertools.combinations(sorted(self.planes), 2):
            if frozenset((first, second)) in has_event or not too_close(self.planes[first], self.planes[second]):
                continue
            event = self.open_event(self.planes[first], self.planes[second])
            if event is not None:
                has_event.add(frozenset((first, second)))

    def open_event(self, a, b):
        """Pick who moves and where, record the event, and send it. None if both planes are already busy."""
        mover = choose_mover(a, b, self.busy, self.holds_runway)
        if mover is None:
            return None  # both are already being moved; look again once they have
        other = b if mover is a else a
        spot = find_spot(mover, other, self.planes)
        status = OPEN if spot is not None else WAITING
        separation_id = open_separation(self.conn, self.airport_id, mover["aircraft_id"], other["aircraft_id"],
                                        spot, status)
        event = {"separation_id": separation_id, "aircraft_id": mover["aircraft_id"],
                 "other_aircraft_id": other["aircraft_id"], "status": status,
                 "move_to_latitude": spot[0] if spot else None, "move_to_longitude": spot[1] if spot else None}
        self.events[separation_id] = event
        self.busy.add(mover["aircraft_id"])
        if spot is not None:
            self.send_move(event)
        else:
            self.to_command(json.dumps(with_severity(move_message(event))))  # command only: no spot for radar yet
        self.changed.append(dict(event))
        return event

    def holds_runway(self, aircraft_id):
        return get_assigned_runway(self.conn, self.airport_id, aircraft_id) is not None
