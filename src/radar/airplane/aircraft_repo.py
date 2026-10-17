# REQ-RAD-012
# aircraft_repo.py — the ONLY radar file that talks to the database.
# It can save a new airplane, look one up, and set its runway (REQ-RAD-013).
#
# How to use it:
#   conn = init_db("radar.db")     # open the database once
#   create_aircraft(conn, plane)   # pass conn in
#   get_aircraft(conn, "AA123")    # returns the plane, or None if there isn't one
#   conn.close()                   # close it when you're done

# sqlite3 is built into Python, so there's nothing extra to install.
import sqlite3
from datetime import datetime

from src.radar.airplane.models import AircraftTelemetry

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
        "status TEXT CHECK(status IN ('Parked','Departing','Landing')), timestamp TEXT, "
        "runway_id TEXT)"  # empty (NULL) until tower assigns a runway
    )
    conn.commit()
    return conn


def create_aircraft(conn, plane):
    """Save a new plane (an AircraftTelemetry). Raises ValueError if that aircraft_id already exists."""
    try:
        # The ? marks are placeholders. SQLite fills them in safely with the values,
        # so nobody can sneak SQL commands in through the data (SQL injection).
        conn.execute(
            "INSERT INTO aircraft (aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (plane.aircraft_id, plane.latitude, plane.longitude, plane.altitude,
             plane.status, plane.timestamp.strftime(TIME_FORMAT), plane.runway_id),  # datetime -> text
        )
    except sqlite3.IntegrityError:
        # The PRIMARY KEY rule blocked a duplicate ID. Nothing was overwritten.
        raise ValueError(f"aircraft {plane.aircraft_id} already exists")
    conn.commit()  # save the change to disk


def get_aircraft(conn, aircraft_id):
    """Return the plane with this ID as an AircraftTelemetry, or None if there isn't one."""
    row = conn.execute(
        "SELECT aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id "
        "FROM aircraft WHERE aircraft_id = ?",
        (aircraft_id,),
    ).fetchone()
    if row is None:
        return None
    aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id = row
    return AircraftTelemetry(
        aircraft_id=aircraft_id,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        status=status,
        timestamp=datetime.strptime(timestamp, TIME_FORMAT),  # text -> datetime
        runway_id=runway_id,
    )


def update_runway(conn, aircraft_id, runway_id):
    """Set the plane's runway and refresh its timestamp to now.

    Raises ValueError if there is no plane with this ID.
    """
    cursor = conn.execute(
        "UPDATE aircraft SET runway_id = ?, timestamp = ? WHERE aircraft_id = ?",
        (runway_id, now().strftime(TIME_FORMAT), aircraft_id),
    )
    if cursor.rowcount == 0:  # rowcount = how many rows were changed
        raise ValueError(f"aircraft {aircraft_id} does not exist")
    conn.commit()
