# REQ-TOW-006, REQ-TOW-007, REQ-TOW-009, REQ-TOW-010, REQ-TOW-011, REQ-TOW-012, REQ-TOW-013
# airport_repo.py — the ONLY tower file that talks to the airport database.
# It can create the tables, add a new airport, assign a runway, and free it again.
#
# How to use it:
#   conn = sqlite3.connect("tower.db")      # open the database once
#   create_tables(conn)                     # safe to call every time
#   create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
#   assign_runway(conn, "JFK", "AA123")     # -> 1 (or None if every runway is taken)
#   free_runway(conn, "JFK", "AA123")       # -> 1 (or None if AA123 had no runway)
#   conn.close()                            # close it when you're done

# NOTE: that doc comment is out of date but, I don't feel like changing it.
# this works exactly the same as it did when there was the wall of sql strings
# those are now in  dedicated .sql files (queries.sql & schema.sql)

# NOTE: changed to StrEnum (string enum) for typo safety, autocomplete, and
# removing clutter of the brackets and quotes

import sqlite3
from functools import cache
from pathlib import Path
from datetime import datetime


from src.tower.messaging.query_fetch import load_queries, load_schema

TIME_FORMAT  = "%Y-%m-%dT%H:%M:%S"
RUNWAY_COUNT = 10


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

def assign_runway(conn, airport_id, aircraft_id, new_status): #new_status="LANDING_ASSIGNED"
    with conn:
        row = conn.execute(QUERIES.get_assignment, (airport_id, aircraft_id)).fetchone()
        if row is not None:
            runway_id = row[0]
            conn.execute(QUERIES.update_assignment_status, (new_status, airport_id, aircraft_id))
            return runway_id

        row = conn.execute(QUERIES.find_available_runway_joint, (airport_id,)).fetchone()
        if row is None:
            return None

        runway_id = row[0]
        conn.execute(QUERIES.insert_runway_assignment, (airport_id, runway_id, aircraft_id, new_status, now()))

    return runway_id

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
