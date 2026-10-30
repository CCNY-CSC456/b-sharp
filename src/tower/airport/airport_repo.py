# REQ-TOW-006, REQ-TOW-007, REQ-TOW-010
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

from functools import cache
from pathlib import Path
import sqlite3
from datetime import datetime


from src.tower.messaging.query_fetch import load_queries, load_schema

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
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

    tables = {row[0] for row in conn.execute(QUERIES["check_tables"])}
    return {"airport", "runways"} <= tables

def create_airport(conn, airport_id, perimeter, latitude, longitude):
    try:
        with conn:
            conn.execute(QUERIES["insert_airport"], (airport_id, perimeter, latitude, longitude))
            timestamp = now()
            conn.executemany(
                QUERIES["insert_runway"],
                [(airport_id, runway_id, "Available", timestamp) for runway_id in range(1, RUNWAY_COUNT + 1)]
            )
    except sqlite3.Error:
        return False
    return True

def is_processed(conn, msg_key):
    row = conn.execute(QUERIES["check_message_processed"], (msg_key,)).fetchone()
    return row is not None

def mark_processed(conn, msg_key):
    with conn:
        conn.execute(QUERIES["mark_message_processed"], (msg_key,))

def assign_runway(conn, airport_id, aircraft_id, new_status="LANDING_ASSIGNED"):
    with conn:
        row = conn.execute(QUERIES["get_assignment"], (airport_id, aircraft_id)).fetchone()
        if row is not None:
            runway_id = row[0]
            conn.execute(QUERIES["update_assignment_status"], (new_status, airport_id, aircraft_id))
            return runway_id

        row = conn.execute(QUERIES["find_available_runway_joint"], (airport_id,)).fetchone()
        if row is None:
            return None

        runway_id = row[0]
        conn.execute(QUERIES["insert_runway_assignment"], (airport_id, runway_id, aircraft_id, new_status, now()))

    return runway_id

def free_runway(conn, airport_id, aircraft_id):
    with conn:
        row = conn.execute(QUERIES["get_assignment"], (airport_id, aircraft_id)).fetchone()
        if row is None:
            return None

        runway_id = row[0]
        conn.execute(QUERIES["delete_assignment"], (airport_id, aircraft_id))
    return runway_id