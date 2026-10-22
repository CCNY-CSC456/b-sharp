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

# sqlite3 is built into Python, so there's nothing extra to install.
import sqlite3
from datetime import datetime

# Timestamps are stored as text that looks like "2026-10-08T14:30:00".
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Every airport gets this many runways, numbered 1 to RUNWAY_COUNT.
RUNWAY_COUNT = 10


def now():
    """The current time as text in TIME_FORMAT."""
    return datetime.now().strftime(TIME_FORMAT)


def create_tables(conn):
    """Create the airport and runways tables if needed. Returns True if both exist afterwards."""
    try:
        # PRIMARY KEY = no two airports can share an airport_id,
        # and no airport can have two runways with the same runway_id.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS airport ("
            "airport_id TEXT PRIMARY KEY, perimeter REAL, latitude REAL, longitude REAL)"
        )
        # CHECK = the database itself refuses any other status.
        # aircraft_id = which airplane has the runway (empty while it's Available).
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runways ("
            "airport_id TEXT, runway_id INTEGER, "
            "status TEXT CHECK(status IN ('Available','Not Available')), timestamp TEXT, "
            "aircraft_id TEXT, "
            "PRIMARY KEY (airport_id, runway_id))"
        )
        conn.commit()
    except sqlite3.Error:
        return False
    # Ask SQLite which tables really exist
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"airport", "runways"} <= tables


def create_airport(conn, airport_id, perimeter, latitude, longitude):
    """Save a new airport with RUNWAY_COUNT runways, all "Available".

    Returns True if it was saved, False if not (for example, the airport_id already exists).
    """
    try:
        # "with conn" saves everything at the end, or undoes everything if any line fails,
        # so we never end up with an airport that is missing some of its runways.
        with conn:
            # The ? marks are placeholders. SQLite fills them in safely with the values,
            # so nobody can sneak SQL commands in through the data (SQL injection).
            conn.execute(
                "INSERT INTO airport VALUES (?, ?, ?, ?)",
                (airport_id, perimeter, latitude, longitude),
            )
            timestamp = now()
            # Columns are named so aircraft_id is left empty: new runways have no airplane yet.
            conn.executemany(
                "INSERT INTO runways (airport_id, runway_id, status, timestamp) VALUES (?, ?, ?, ?)",
                [(airport_id, runway_id, "Available", timestamp) for runway_id in range(1, RUNWAY_COUNT + 1)],
            )
    except sqlite3.Error:
        return False
    return True


def assign_runway(conn, airport_id, aircraft_id):
    """Give an airplane a runway at this airport. Returns the runway_id, or None if none is free.

    The lowest-numbered "Available" runway is used. It becomes "Not Available" and remembers the airplane.
    If the airplane already has a runway, that same runway is returned and nothing changes.
    That matters because tower's inbox keeps every message, so the same request can be read twice.
    """
    # "with conn" makes the look-up and the update one step: either both happen or neither does.
    with conn:
        # Already has a runway? Give back the same one instead of taking a second.
        row = conn.execute(
            "SELECT runway_id FROM runways WHERE airport_id = ? AND aircraft_id = ?",
            (airport_id, aircraft_id),
        ).fetchone()
        if row is not None:
            return row[0]

        # Find the lowest-numbered free runway.
        row = conn.execute(
            "SELECT runway_id FROM runways WHERE airport_id = ? AND status = 'Available' "
            "ORDER BY runway_id LIMIT 1",
            (airport_id,),
        ).fetchone()
        if row is None:  # every runway is taken, or there's no such airport
            return None
        runway_id = row[0]

        # "AND status = 'Available'" means this only changes the runway if it's still free,
        # so two airplanes can never end up on the same runway.
        conn.execute(
            "UPDATE runways SET status = 'Not Available', aircraft_id = ?, timestamp = ? "
            "WHERE airport_id = ? AND runway_id = ? AND status = 'Available'",
            (aircraft_id, now(), airport_id, runway_id),
        )
    return runway_id


def free_runway(conn, airport_id, aircraft_id):
    """Free the runway an airplane holds at this airport. Returns that runway_id, or None.

    The runway goes back to "Available" with no airplane, so assign_runway() can give it out again.
    None means the airplane had no runway here, so nothing changed. Freeing twice is harmless,
    which matters because tower's inbox keeps every message, so the same "landed" can be read twice.
    """
    # "with conn" makes the look-up and the update one step: either both happen or neither does.
    with conn:
        row = conn.execute(
            "SELECT runway_id FROM runways WHERE airport_id = ? AND aircraft_id = ?",
            (airport_id, aircraft_id),
        ).fetchone()
        if row is None:  # this airplane has no runway here
            return None
        runway_id = row[0]

        conn.execute(
            "UPDATE runways SET status = 'Available', aircraft_id = NULL, timestamp = ? "
            "WHERE airport_id = ? AND runway_id = ?",
            (now(), airport_id, runway_id),
        )
    return runway_id
