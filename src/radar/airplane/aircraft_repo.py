# REQ-RAD-012
# aircraft_repo.py — the ONLY radar file that talks to the database.
# It can save a new airplane, look one up, set its runway (REQ-RAD-013),
# delete it (REQ-RAD-014), change its altitude (REQ-RAD-015), and keep the R2 tables
# (handled tower messages, conflicts, runway timers: REQ-RAD-017, REQ-RAD-018, REQ-RAD-019).
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
from src.tower.messaging.query_fetch import load_queries

# Timestamps are stored as text that looks like "2026-10-08T14:30:00".
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

QUERIES     = load_queries("queries.sql")

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
    conn.execute( QUERIES.RDR_A_00  )# empty (NULL) until tower assigns a runway
    init_r2_tables(conn)  # radar's R2 tables (see the bottom of this file)
    conn.commit()
    return conn


def create_aircraft(conn, plane):
    """Save a new plane (an AircraftTelemetry). Raises ValueError if that aircraft_id already exists."""
    try:
        # The ? marks are placeholders. SQLite fills them in safely with the values,
        # so nobody can sneak SQL commands in through the data (SQL injection).
        conn.execute( QUERIES.RDR_A_01,
            (plane.aircraft_id, plane.latitude, plane.longitude, plane.altitude,
             plane.status, plane.timestamp.strftime(TIME_FORMAT), plane.runway_id),  # datetime -> text
        )
    except sqlite3.IntegrityError:
        # The PRIMARY KEY rule blocked a duplicate ID. Nothing was overwritten.
        raise ValueError(f"aircraft {plane.aircraft_id} already exists")
    conn.commit()  # save the change to disk


def get_aircraft(conn, aircraft_id):
    """Return the plane with this ID as an AircraftTelemetry, or None if there isn't one."""
    row = conn.execute( QUERIES.RDR_A_02, (aircraft_id,), ).fetchone()
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
    cursor = conn.execute( QUERIES.RDR_A_03,
        (runway_id, now().strftime(TIME_FORMAT), aircraft_id),
    )
    if cursor.rowcount == 0:  # rowcount = how many rows were changed
        raise ValueError(f"aircraft {aircraft_id} does not exist")
    conn.commit()


# REQ-RAD-014
def delete_aircraft(conn, aircraft_id):
    """Remove the plane with this ID. Raises ValueError if there is no plane with this ID."""
    cursor = conn.execute(QUERIES.RDR_A_04, (aircraft_id,))
    if cursor.rowcount == 0:  # rowcount = how many rows were deleted
        raise ValueError(f"aircraft {aircraft_id} does not exist")
    conn.commit()


# REQ-RAD-015
def update_altitude(conn, aircraft_id, altitude):
    """Set the plane's altitude (feet) and refresh its timestamp to now.

    Raises ValueError if the altitude is negative or there is no plane with this ID.
    """
    if altitude < 0:
        raise ValueError("altitude can't be negative")
    cursor = conn.execute( QUERIES.RDR_A_05,
        (altitude, now().strftime(TIME_FORMAT), aircraft_id),
    )
    if cursor.rowcount == 0:
        raise ValueError(f"aircraft {aircraft_id} does not exist")
    conn.commit()


# --- R2 (REQ-RAD-017, REQ-RAD-018, REQ-RAD-019) ---
# These tables are radar's own, so their SQL lives here instead of in tower's queries.sql.
# init_db creates them with CREATE TABLE IF NOT EXISTS, so an existing radar.db keeps working (no rm radar.db).

R2_TABLES = (
    # Tower messages radar has already acted on. Radar's inbox returns EVERY message ever sent,
    # so this is how an old message is not acted on twice.
    "CREATE TABLE IF NOT EXISTS handled_messages (message_key TEXT PRIMARY KEY)",
    # Conflict signals (REQ-RAD-018). status is OPEN until tower sends CONFLICT_RESOLVED.
    "CREATE TABLE IF NOT EXISTS conflicts (conflict_id TEXT PRIMARY KEY, aircraft_id TEXT, reason TEXT, "
    "status TEXT CHECK(status IN ('OPEN','RESOLVED')), opened_at TEXT, resolved_at TEXT)",
    # The 30 second wait after a runway assignment (REQ-RAD-019). done = 1 once LANDED/DEPARTED was sent.
    "CREATE TABLE IF NOT EXISTS runway_timers (timer_key TEXT PRIMARY KEY, aircraft_id TEXT, runway_id TEXT, "
    "request TEXT, assigned_at TEXT, done INTEGER DEFAULT 0)",
    # When each plane last departed: a new flight starts there (tower counts conflicts per flight, REQ-TOW-015).
    "CREATE TABLE IF NOT EXISTS departures (aircraft_id TEXT PRIMARY KEY, departed_at TEXT)",
)


def init_r2_tables(conn):
    for statement in R2_TABLES:
        conn.execute(statement)
    conn.commit()


def changed_one_row(cursor, aircraft_id):
    if cursor.rowcount == 0:
        raise ValueError(f"aircraft {aircraft_id} does not exist")


# REQ-RAD-017, REQ-RAD-020
def update_position(conn, aircraft_id, latitude, longitude, clock=now):
    """Set the plane's latitude and longitude and refresh its timestamp.

    Raises ValueError if the position is off the globe or there's no such plane.
    """
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
    cursor = conn.execute("UPDATE aircraft SET latitude = ?, longitude = ?, timestamp = ? WHERE aircraft_id = ?",
                          (latitude, longitude, clock().strftime(TIME_FORMAT), aircraft_id))
    changed_one_row(cursor, aircraft_id)
    conn.commit()


# REQ-RAD-019
def update_landed(conn, aircraft_id, clock=now):
    """The plane is on the ground and parked: status Parked, altitude 0, no runway."""
    cursor = conn.execute("UPDATE aircraft SET status = 'Parked', altitude = 0, runway_id = NULL, timestamp = ? "
                          "WHERE aircraft_id = ?", (clock().strftime(TIME_FORMAT), aircraft_id))
    changed_one_row(cursor, aircraft_id)
    conn.commit()


def clear_runway(conn, aircraft_id, clock=now):
    """The plane has left its runway."""
    cursor = conn.execute("UPDATE aircraft SET runway_id = NULL, timestamp = ? WHERE aircraft_id = ?",
                          (clock().strftime(TIME_FORMAT), aircraft_id))
    changed_one_row(cursor, aircraft_id)
    conn.commit()


# REQ-RAD-018
def touch_aircraft(conn, aircraft_id, clock=now):
    """Refresh the plane's timestamp (its data was just updated)."""
    cursor = conn.execute("UPDATE aircraft SET timestamp = ? WHERE aircraft_id = ?",
                          (clock().strftime(TIME_FORMAT), aircraft_id))
    changed_one_row(cursor, aircraft_id)
    conn.commit()


# --- handled tower messages ---

def is_handled(conn, message_key):
    return conn.execute("SELECT 1 FROM handled_messages WHERE message_key = ?", (message_key,)).fetchone() is not None


def mark_handled(conn, message_key):
    conn.execute("INSERT OR IGNORE INTO handled_messages (message_key) VALUES (?)", (message_key,))
    conn.commit()


# --- conflicts (REQ-RAD-018) ---

CONFLICT_COLUMNS = ("conflict_id", "aircraft_id", "reason", "status", "opened_at", "resolved_at")


def insert_conflict(conn, conflict_id, aircraft_id, reason, opened_at):
    """Save a new OPEN conflict. ValueError if this plane already has this reason open."""
    if conn.execute("SELECT 1 FROM conflicts WHERE aircraft_id = ? AND reason = ? AND status = 'OPEN'",
                    (aircraft_id, reason)).fetchone():
        raise ValueError(f"aircraft {aircraft_id} already has an open {reason} conflict")
    try:
        conn.execute("INSERT INTO conflicts (conflict_id, aircraft_id, reason, status, opened_at) "
                     "VALUES (?, ?, ?, 'OPEN', ?)", (conflict_id, aircraft_id, reason, opened_at))
    except sqlite3.IntegrityError:
        raise ValueError(f"conflict {conflict_id} already exists")
    conn.commit()


def select_conflicts(conn, status=None):
    """Every conflict (or only those with this status) as dicts, oldest first."""
    sql = f"SELECT {', '.join(CONFLICT_COLUMNS)} FROM conflicts"
    rows = (conn.execute(sql + " WHERE status = ? ORDER BY rowid", (status,)) if status
            else conn.execute(sql + " ORDER BY rowid"))
    return [dict(zip(CONFLICT_COLUMNS, row)) for row in rows]


def latest_flight_conflict(conn, aircraft_id, reason):
    """The status of this plane's newest conflict with this reason since it last departed, or None."""
    row = conn.execute("SELECT status FROM conflicts WHERE aircraft_id = ? AND reason = ? AND opened_at > "
                       "COALESCE((SELECT departed_at FROM departures WHERE aircraft_id = ?), '') "
                       "ORDER BY rowid DESC LIMIT 1", (aircraft_id, reason, aircraft_id)).fetchone()
    return row[0] if row else None


def record_departure(conn, aircraft_id, departed_at):
    conn.execute("INSERT OR REPLACE INTO departures (aircraft_id, departed_at) VALUES (?, ?)",
                 (aircraft_id, departed_at))
    conn.commit()


def close_conflict(conn, conflict_id, aircraft_id, resolved_at):
    """OPEN -> RESOLVED. Returns True if it was open (and belongs to this plane)."""
    cursor = conn.execute("UPDATE conflicts SET status = 'RESOLVED', resolved_at = ? "
                          "WHERE conflict_id = ? AND aircraft_id = ? AND status = 'OPEN'",
                          (resolved_at, conflict_id, aircraft_id))
    conn.commit()
    return cursor.rowcount == 1


# --- runway timers (REQ-RAD-019) ---

TIMER_COLUMNS = ("timer_key", "aircraft_id", "runway_id", "request", "assigned_at")


def insert_runway_timer(conn, timer_key, aircraft_id, runway_id, request, assigned_at):
    """Start a wait. Returns False if this assignment already has one."""
    cursor = conn.execute("INSERT OR IGNORE INTO runway_timers (timer_key, aircraft_id, runway_id, request, "
                          "assigned_at) VALUES (?, ?, ?, ?, ?)", (timer_key, aircraft_id, runway_id, request, assigned_at))
    conn.commit()
    return cursor.rowcount == 1


def select_due_timers(conn, assigned_before):
    """Unfinished waits that started at or before `assigned_before` (TIME_FORMAT text sorts by time)."""
    rows = conn.execute(f"SELECT {', '.join(TIMER_COLUMNS)} FROM runway_timers "
                        "WHERE done = 0 AND assigned_at <= ? ORDER BY assigned_at, rowid", (assigned_before,))
    return [dict(zip(TIMER_COLUMNS, row)) for row in rows]


def finish_runway_timer(conn, timer_key):
    conn.execute("UPDATE runway_timers SET done = 1 WHERE timer_key = ?", (timer_key,))
    conn.commit()
