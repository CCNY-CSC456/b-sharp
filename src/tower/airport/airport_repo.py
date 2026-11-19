# REQ-TOW-006, REQ-TOW-007, REQ-TOW-009, REQ-TOW-010, REQ-TOW-011, REQ-TOW-012, REQ-TOW-013, REQ-TOW-014, REQ-TOW-015
# airport_repo.py — the ONLY tower file that talks to the airport database.
# It creates the tables, adds an airport, assigns / frees runways, and remembers which messages it handled.
# The SQL itself lives in src/tower/sql/ (schema.sql for the tables, queries.sql for every query by name).
#
# How to use it:
#   conn = sqlite3.connect("tower.db")                       # open the database once
#   create_tables(conn)                                      # safe to call every time
#   create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
#   assign_runway(conn, "JFK", "AA123", "LANDING_ASSIGNED")  # -> 1 (None if every runway is taken;
#                                                            #    InvalidRunwayTransition if the phase can't change)
#   set_assignment_status(conn, "JFK", "AA123", "LANDED")    # same runway, new phase
#   free_runway(conn, "JFK", "AA123")                        # -> 1 (or None if AA123 had no runway)
#   conn.close()                                             # close it when you're done

# NOTE: changed to StrEnum (string enum) for typo safety, autocomplete, and
# removing clutter of the brackets and quotes

import sqlite3
from functools import cache
from pathlib import Path
from datetime import datetime
import json

from src.tower.messaging.query_fetch import load_queries, load_schema

TIME_FORMAT  = "%Y-%m-%dT%H:%M:%S"
RUNWAY_COUNT = 20


QUERIES     = load_queries("queries.sql")
INIT_SCHEMA = load_schema("schema.sql")

def now():
    return datetime.now().strftime(TIME_FORMAT)

def create_tables(conn):
    try:
        conn.executescript(INIT_SCHEMA)
        conn.commit()
    except sqlite3.Error:
        return False

    tables = {row[0] for row in conn.execute(QUERIES.check_tables)}
    return {"airport", "runways"} <= tables

def create_airport(conn, airport_id, perimeter, latitude, longitude):
    try:
        with conn:
            conn.execute(QUERIES.insert_airport, (airport_id, perimeter, latitude, longitude))
            timestamp = now()
            conn.executemany(
                QUERIES.insert_runway,
                [(airport_id, runway_id, "Available", timestamp) for runway_id in range(1, RUNWAY_COUNT + 1)]
            )
    except sqlite3.Error:
        return False
    return True

def is_processed(conn, msg_key):
    row = conn.execute(QUERIES.check_message_processed, (msg_key,)).fetchone()
    return row is not None

def mark_processed(conn, msg_key):
    with conn:
        conn.execute(QUERIES.mark_message_processed, (msg_key,))



# Allowed changes to a runway assignment's phase (REQ-TOW-011). None = the plane holds no runway yet.
# PARKED and DEPARTED aren't phases: they free the runway, which deletes the assignment.
VALID_TRANSITIONS = {
    (None, "LANDING_ASSIGNED"),               # first landing clearance
    (None, "TAKEOFF_ASSIGNED"),               # first takeoff clearance (plane starts on the ground)
    ("LANDING_ASSIGNED", "LANDING_ASSIGNED"), # landing clearance asked for again
    ("LANDING_ASSIGNED", "LANDED"),           # plane touches down
    ("LANDED", "LANDED"),                     # landing reported again
    ("LANDED", "TAKEOFF_ASSIGNED"),           # plane asks to take off after landing
    ("TAKEOFF_ASSIGNED", "TAKEOFF_ASSIGNED"), # takeoff clearance asked for again
}
# Not sure that's right but will have to check hence ugly comment out


class InvalidRunwayTransition(ValueError):
    """A request that would move a plane's runway phase in a way VALID_TRANSITIONS doesn't allow."""

    def __init__(self, aircraft_id, current_status, new_status):
        super().__init__(f"Invalid FSM transition for aircraft '{aircraft_id}': "
                         f"cannot transition from '{current_status}' to '{new_status}'.")
        self.aircraft_id, self.current_status, self.new_status = aircraft_id, current_status, new_status


# validate whether a runway assignment state transition is permitted.
def validate_runway_transition(current_status: str | None, new_status: str) -> bool:
    return (current_status, new_status) in VALID_TRANSITIONS


def assign_runway(conn, airport_id, aircraft_id, new_status="LANDING_ASSIGNED"):
    if conn.in_transaction:
        conn.commit()

    conn.execute("BEGIN IMMEDIATE") # NOTE we had (or have) a "Non-Atomic Check-Then-Act" which this MAYBE addresses
    try:       # basically same query v but with status, old one might be unused now
        row = conn.execute(QUERIES.get_assignment_and_status, (airport_id, aircraft_id)).fetchone()
        current_status = row[1] if row else None
        if not validate_runway_transition(current_status, new_status):
            conn.commit()  # nothing was changed; end the transaction before refusing
            raise InvalidRunwayTransition(aircraft_id, current_status, new_status)  # caller refuses the request

        if row is not None:
            runway_id = row[0]
            if current_status != new_status: # this one's since if it's an indempotent request, just no-op it
                conn.execute(QUERIES.update_assignment_status, (new_status, airport_id, aircraft_id))
            conn.commit()
            return runway_id

        row = conn.execute(QUERIES.find_available_runway_joint, (airport_id,)).fetchone()
        if row is None:
            conn.commit()
            return None

        runway_id = row[0]
        conn.execute(QUERIES.insert_runway_assignment, (airport_id, runway_id, aircraft_id, new_status, now()))
        conn.commit()
        return runway_id
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise

def free_runway(conn, airport_id, aircraft_id):
    with conn:
        row = conn.execute(QUERIES.get_assignment, (airport_id, aircraft_id)).fetchone()
        if row is None:
            return None

        runway_id = row[0]
        conn.execute(QUERIES.delete_assignment, (airport_id, aircraft_id))
    return runway_id

def get_assigned_runway(conn, airport_id, aircraft_id):
    """The runway this plane holds right now, or None. Read only (REQ-TOW-009)."""
    row = conn.execute(QUERIES.get_assignment, (airport_id, aircraft_id)).fetchone()
    return None if row is None else row[0]

def set_assignment_status(conn, airport_id, aircraft_id, status):
    """Change the phase of the runway this plane holds (e.g. LANDED). Does nothing if it holds none (REQ-TOW-011)."""
    with conn:
        conn.execute(QUERIES.update_assignment_status, (status, airport_id, aircraft_id))

def get_runway_status(conn, airport_id):
    """Every runway as (runway_id, aircraft_id, phase); a free runway has None for both (REQ-TOW-012)."""
    return conn.execute(QUERIES.get_runway_status, (airport_id,)).fetchall()

def get_sent_runway_status(conn, airport_id):
    """What tower last told command about each runway: {runway_id: (aircraft_id, phase)} (REQ-TOW-012)."""
    rows = conn.execute(QUERIES.get_sent_runway_status, (airport_id,))
    return {runway_id: (aircraft_id, phase) for runway_id, aircraft_id, phase in rows}

def record_sent_runway_status(conn, airport_id, runway_id, aircraft_id, phase):
    """Remember what tower just told command about this runway (REQ-TOW-012)."""
    with conn:
        conn.execute(QUERIES.record_sent_runway_status, (airport_id, runway_id, aircraft_id, phase))

def save_aircraft_positions(conn, airport_id, planes):
    """Replace the stored positions with `planes` (dicts with the aircraft_positions columns) (REQ-TOW-013)."""
    with conn:
        conn.execute(QUERIES.clear_aircraft_positions, (airport_id,))
        conn.executemany(QUERIES.insert_aircraft_position, [
            (airport_id, p["aircraft_id"], p["latitude"], p["longitude"], p["altitude"], p["status"],
             1 if p["on_ground"] else 0, p["requested_at"], p["timestamp"])
            for p in planes
        ])

def get_aircraft_positions(conn, airport_id):
    """Every stored plane as a dict, sorted by aircraft_id (REQ-TOW-013)."""
    columns = ("aircraft_id", "latitude", "longitude", "altitude", "status", "on_ground", "requested_at", "timestamp")
    rows = conn.execute(QUERIES.get_aircraft_positions, (airport_id,))
    return [dict(zip(columns, row), on_ground=bool(row[5])) for row in rows]

def get_separations(conn, airport_id):
    """Every separation event as a dict, oldest first (REQ-TOW-013)."""
    columns = ("separation_id", "aircraft_id", "other_aircraft_id", "move_to_latitude", "move_to_longitude",
               "status", "opened_at", "resolved_at")
    return [dict(zip(columns, row)) for row in conn.execute(QUERIES.get_separations, (airport_id,))]

def open_separation(conn, airport_id, aircraft_id, other_aircraft_id, move_to, status):
    """Record a new separation event and return its separation_id (REQ-TOW-013).

    move_to is (latitude, longitude), or None when there is no clear spot yet (status WAITING).
    """
    latitude, longitude = move_to if move_to is not None else (None, None)
    with conn:
        cursor = conn.execute(QUERIES.insert_separation,
                              (airport_id, aircraft_id, other_aircraft_id, latitude, longitude, status, now()))
    return cursor.lastrowid

def set_separation_move_to(conn, airport_id, separation_id, move_to):
    """A WAITING event found its clear spot: store it and mark the event OPEN (REQ-TOW-013)."""
    with conn:
        conn.execute(QUERIES.set_separation_move_to, (move_to[0], move_to[1], airport_id, separation_id))

def close_separation(conn, airport_id, separation_id, status):
    """Mark a WAITING/OPEN event RESOLVED or CANCELLED. Returns True if it was still open (REQ-TOW-013)."""
    with conn:
        cursor = conn.execute(QUERIES.close_separation, (status, now(), airport_id, separation_id))
    return cursor.rowcount == 1


# --- REQ-TOW-014: the saved runway queue and the reply outbox (used by scheduler.py) ---

def get_request_queue(conn, airport_id):
    columns = ("queue_id", "aircraft_id", "req_type", "req_timestamp", "msg_key", "position", "created_at")
    rows = conn.execute(QUERIES.get_request_queue, (airport_id,))
    return [dict(zip(columns, row)) for row in rows]


def save_request_queue(conn, airport_id, items):
    """Persist ordered queue entries `(aircraft_id, req_type, req_timestamp, msg_key)` for `airport_id`."""
    ts = now()
    with conn:
        conn.execute(QUERIES.replace_request_queue, (airport_id,))
        conn.executemany(
            QUERIES.insert_request_queue,
            [
                (airport_id, item["aircraft_id"], item["req_type"], item.get("req_timestamp"), item["msg_key"], idx, ts)
                for idx, item in enumerate(items)
            ],
        )


def remove_queued_request(conn, airport_id, aircraft_id):
    with conn:
        conn.execute(QUERIES.delete_request_queue_by_aircraft, (airport_id, aircraft_id))


def enqueue_response(conn, airport_id, target, payload):
    with conn:
        cursor = conn.execute(
            QUERIES.insert_response_queue,
            (airport_id, target, json.dumps(payload), now()),
        )
    return cursor.lastrowid


def get_response_queue(conn, airport_id):
    columns = ("response_id", "target", "payload_json", "created_at")
    rows = conn.execute(QUERIES.get_response_queue, (airport_id,))
    return [
        {
            "response_id": row[0],
            "target": row[1],
            "payload": json.loads(row[2]),
            "created_at": row[3],
        }
        for row in rows
    ]


def remove_queued_response(conn, airport_id, response_id):
    with conn:
        conn.execute(QUERIES.delete_response_queue_item, (response_id, airport_id))


# --- REQ-TOW-015: conflicts radar reports (late / low on gas) ---

def get_conflicts(conn, airport_id):
    """Every conflict as a dict, oldest first."""
    columns = ("conflict_id", "aircraft_id", "reason", "first_reported_at", "spots", "status", "opened_at", "resolved_at")
    return [dict(zip(columns, row)) for row in conn.execute(QUERIES.get_conflicts, (airport_id,))]


def open_conflict(conn, airport_id, aircraft_id, reason, first_reported_at, spots):
    """Record a new PENDING conflict and return its conflict_id."""
    with conn:
        cursor = conn.execute(QUERIES.insert_conflict,
                              (airport_id, aircraft_id, reason, first_reported_at, spots, now()))
    return cursor.lastrowid


def resolve_conflict(conn, airport_id, conflict_id):
    """Mark a PENDING conflict RESOLVED. Returns True if it was still pending."""
    with conn:
        cursor = conn.execute(QUERIES.resolve_conflict, (now(), airport_id, conflict_id))
    return cursor.rowcount == 1



# bro we need to be able to change runways oh snap
def set_runway_count(conn, airport_id, runway_count):
    """Demo helper: update airport.runway_count and sync/trim runways in one transaction.

    Returns the resulting runway count in `runways` for `airport_id`, or None if the
    airport does not exist.
    """
    if isinstance(runway_count, bool) or not isinstance(runway_count, int) or runway_count <= 0:
        raise ValueError(f"runway_count must be a positive integer, got {runway_count!r}")

    if conn.in_transaction:
        conn.commit()

    timestamp = now()
    with conn:
        cur = conn.execute(QUERIES.update_airport_runway_count, (runway_count, airport_id))
        if cur.rowcount == 0:
            return None

        conn.execute(
            QUERIES.sync_runways_up,
            (airport_id, airport_id, timestamp),
        )
        conn.execute(
            QUERIES.trim_excess_runways,
            (airport_id, airport_id),
        )

    row = conn.execute(QUERIES.last_runway_resync, (airport_id,), ).fetchone()
    return row[0] if row else 0
