# REQ-TOW-006
# airport_repo.py — the ONLY tower file that talks to the airport database.
# For now it can only create the tables and add a new airport. Get, update, and delete come later.
#
# How to use it:
#   conn = sqlite3.connect("tower.db")      # open the database once
#   create_tables(conn)                     # safe to call every time
#   create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
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
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runways ("
            "airport_id TEXT, runway_id INTEGER, "
            "status TEXT CHECK(status IN ('Available','Not Available')), timestamp TEXT, "
            "PRIMARY KEY (airport_id, runway_id))"
        )
        conn.commit()
    except sqlite3.Error:
        return False
    # Ask SQLite which tables really exist, instead of assuming it worked.
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
            conn.executemany(
                "INSERT INTO runways VALUES (?, ?, ?, ?)",
                [(airport_id, runway_id, "Available", timestamp) for runway_id in range(1, RUNWAY_COUNT + 1)],
            )
    except sqlite3.Error:
        return False
    return True
