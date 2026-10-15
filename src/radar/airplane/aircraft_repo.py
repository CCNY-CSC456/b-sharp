# REQ-RAD-012
# aircraft_repo.py — the ONLY radar file that talks to the database.
# For now it can only save a new airplane. Get, update, and delete come later.
#
# How to use it:
#   conn = init_db("radar.db")     # open the database once
#   create_aircraft(conn, plane)   # pass conn in
#   conn.close()                   # close it when you're done

# sqlite3 is built into Python, so there's nothing extra to install.
import sqlite3
from datetime import datetime

# Timestamps are stored as text that looks like "2026-10-08T14:30:00".
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def now():
    """The current time, cut to whole seconds so it fits TIME_FORMAT exactly."""
    return datetime.now().replace(microsecond=0)


def init_db(db_path="radar.db"):
    """Open the database, create the aircraft table if needed, and return the connection.

    Tests pass ":memory:" to get a throwaway database that lives only in RAM.
    The caller is responsible for calling conn.close() when finished.
    """
    conn = sqlite3.connect(db_path)
    # PRIMARY KEY = no two planes can share an aircraft_id.
    # CHECK = the database itself refuses any other status (a second safety net).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS aircraft ("
        "aircraft_id TEXT PRIMARY KEY, latitude REAL, longitude REAL, altitude REAL, "
        "status TEXT CHECK(status IN ('Parked','Departing','Landing')), timestamp TEXT)"
    )
    conn.commit()
    return conn


def create_aircraft(conn, plane):
    """Save a new plane (an AircraftTelemetry). Raises ValueError if that aircraft_id already exists."""
    try:
        # The ? marks are placeholders. SQLite fills them in safely with the values,
        # so nobody can sneak SQL commands in through the data (SQL injection).
        conn.execute(
            "INSERT INTO aircraft VALUES (?, ?, ?, ?, ?, ?)",
            (plane.aircraft_id, plane.latitude, plane.longitude, plane.altitude,
             plane.status, plane.timestamp.strftime(TIME_FORMAT)),  # datetime -> text
        )
    except sqlite3.IntegrityError:
        # The PRIMARY KEY rule blocked a duplicate ID. Nothing was overwritten.
        raise ValueError(f"aircraft {plane.aircraft_id} already exists")
    conn.commit()  # save the change to disk
