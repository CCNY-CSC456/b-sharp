# REQ-TOW-006, REQ-TOW-007
# airport_repo.py — the ONLY tower file that talks to the airport database.
# It can create the tables, add a new airport, and assign a runway. Freeing runways comes later.
#
# How to use it:
#   conn = sqlite3.connect("tower.db")      # open the database once
#   create_tables(conn)                     # safe to call every time
#   create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
#   assign_runway(conn, "JFK", "AA123")     # -> 1 (or None if every runway is taken)
#   conn.close()                            # close it when you're done

# sqlite3 is built into Python, so there's nothing extra to install.
import sqlite3
from datetime import datetime

# Timestamps are stored as text that looks like "2026-10-08T14:30:00".
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Every airport gets this many runways, numbered 1 to RUNWAY_COUNT.
RUNWAY_COUNT = 10

HQC = [0, 1, 2, 3, 4, 5, 6, 7];

# PRIMARY KEY = no two airports can share an airport_id,
# and no airport can have two runways with the same runway_id.
HQC[0] = """
    CREATE TABLE IF NOT EXISTS airport (
    airport_id TEXT PRIMARY KEY, perimeter REAL, latitude REAL, longitude REAL)
"""

# CHECK = the database itself refuses any other status.
# aircraft_id = which airplane has the runway (empty while it's Available).
HQC[1] = """
            CREATE TABLE IF NOT EXISTS runways (
            airport_id TEXT, runway_id INTEGER,
            status TEXT CHECK(status IN ('Available','Not Available')), timestamp TEXT,
            aircraft_id TEXT,
            PRIMARY KEY (airport_id, runway_id))
"""

# this is a standard "what tables are in this database" query
HQC[2] = """
    SELECT name FROM sqlite_master WHERE type='table'
"""

# The ? marks are placeholders. SQLite fills them in safely with the values,
# so nobody can sneak SQL commands in through the data (SQL injection).
HQC[3] = """
    INSERT INTO airport VALUES (?, ?, ?, ?)
"""

# Columns are named so aircraft_id is left empty: new runways have no airplane yet.
HQC[4] = """
    INSERT INTO runways (airport_id, runway_id, status, timestamp) VALUES (?, ?, ?, ?)
"""

# Already has a runway? Give back the same one instead of taking a second.
HQC[5] = """
    SELECT runway_id FROM runways WHERE airport_id = ? AND aircraft_id = ?
"""

# Find the lowest-numbered free runway.
HQC[6] = """
    SELECT runway_id FROM runways WHERE airport_id = ? AND status = 'Available'
    ORDER BY runway_id LIMIT 1
"""

# "AND status = 'Available'" means this only changes the runway if it's still free,
# so two airplanes can never end up on the same runway.
HQC[7] = """
    UPDATE runways SET status = 'Not Available', aircraft_id = ?, timestamp = ?
    WHERE airport_id = ? AND runway_id = ? AND status = 'Available'
"""



def now():
    """The current time as text in TIME_FORMAT."""
    return datetime.now().strftime(TIME_FORMAT)


def create_tables(conn):
    """Create the airport and runways tables if needed. Returns True if both exist afterwards."""
    try:
        conn.execute( HQC[0] )
        conn.execute( HQC[1] )
        conn.commit()
    except sqlite3.Error:
        return False
    # Ask SQLite which tables really exist
    tables = {row[0] for row in conn.execute( HQC[2] )}
    return {"airport", "runways"} <= tables


def create_airport(conn, airport_id, perimeter, latitude, longitude):
    """Save a new airport with RUNWAY_COUNT runways, all "Available".

    Returns True if it was saved, False if not (for example, the airport_id already exists).
    """
    try:
        with conn: # "with" block makes it transactional, no half-built airport
            conn.execute( HQC[3], (airport_id, perimeter, latitude, longitude), )

            timestamp = now()
            conn.executemany( HQC[4],
                [(airport_id, runway_id, "Available", timestamp)
                 for runway_id in range(1, RUNWAY_COUNT + 1)],
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
    with conn: # with block for look-up & update both in one transaction

        row = conn.execute( HQC[5],(airport_id, aircraft_id), ).fetchone()
        if row is not None:
            return row[0]

        row = conn.execute( HQC[6], (airport_id,), ).fetchone()
        if row is None:  # every runway is taken, or there's no such airport
            return None
        runway_id = row[0]

        conn.execute( HQC[7], (aircraft_id, now(), airport_id, runway_id), )
    return runway_id
