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

# HQC = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, ];
HQC = []

for i in range(1,100):
  HQC.insert(i,i)

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

HQC[8] = """
SELECT runway_id FROM runways WHERE airport_id = ? AND aircraft_id = ?
"""

HQC[9] = """
UPDATE runways SET status = 'Available', aircraft_id = NULL, timestamp = ?
WHERE airport_id = ? AND runway_id = ?
"""

HQC[10] = """
CREATE TABLE IF NOT EXISTS processed_messages (message_id TEXT PRIMARY KEY);
"""

HQC[11] = """
-- Dynamic assignments (1:1 constraint between runway and aircraft)
CREATE TABLE IF NOT EXISTS runway_assignments (
    airport_id TEXT NOT NULL,
    runway_id INTEGER NOT NULL UNIQUE,
    aircraft_id TEXT NOT NULL UNIQUE,
    status TEXT CHECK(status IN ('LANDING_ASSIGNED', 'LANDED', 'TAKEOFF_ASSIGNED')),
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (airport_id, runway_id)
);
"""

HQC[12] = """
CREATE VIEW IF NOT EXISTS runway_assignments_json AS
SELECT json_pretty(
    json_group_array(
        json_object(
            'airport_id', airport_id,
            'runway_id', runway_id,
            'aircraft_id', aircraft_id,
            'status', status,
            'assigned_at', assigned_at
        )
    )
) AS json_dump
FROM runway_assignments;
"""


HQC[13] = """
      SELECT r.runway_id
      FROM runways r
      LEFT JOIN runway_assignments ra
             ON r.airport_id = ra.airport_id AND r.runway_id = ra.runway_id
      WHERE r.airport_id = ?
        AND r.status = 'Available'
        AND ra.runway_id IS NULL
      ORDER BY r.runway_id LIMIT 1
"""


HQC[14] = """
        CREATE TABLE IF NOT EXISTS ACTIVE (
        aircraft_id TEXT PRIMARY KEY, latitude REAL, longitude REAL, altitude REAL,
        status TEXT CHECK(status IN ('Parked','Departing','Landing')), timestamp TEXT,
        runway_id TEXT)
"""

HQC[15] =  """
    INSERT INTO runway_assignments (airport_id, runway_id, aircraft_id, status, assigned_at)
    VALUES (?, ?, ?, ?, ?)
"""

HQC[16] = """
      SELECT runway_id FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?
"""

HQC[17] = """
      UPDATE runway_assignments SET status = ? WHERE airport_id = ? AND aircraft_id = ?
"""

HQC[18] = """
      DELETE FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?
"""

HQC[19] = """
    INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)
"""


# NOTE: "with conn:" blocks are for making things transactional(*)          *ish


def now():
    """The current time as text in TIME_FORMAT."""
    return datetime.now().strftime(TIME_FORMAT)


def create_tables(conn):
    """Create the airport and runways tables if needed. Returns True if both exist afterwards."""
    try:
        conn.execute( HQC[0]  )
        conn.execute( HQC[1]  )
        conn.execute( HQC[10] )
        conn.execute( HQC[11] )
        conn.execute( HQC[12] )
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
        with conn:
            conn.execute( HQC[3], (airport_id, perimeter, latitude, longitude), )

            timestamp = now()
            conn.executemany( HQC[4],
                [(airport_id, runway_id, "Available", timestamp)
                 for runway_id in range(1, RUNWAY_COUNT + 1)],
            )
    except sqlite3.Error:
        return False
    return True


# check if a message key has already been handled
def is_processed(conn, msg_key):
  row = conn.execute(
    "SELECT 1 FROM processed_messages WHERE message_id = ?", (msg_key,)
  ).fetchone()
  return row is not None

# record a message key to guarantee idempotency across executions.
def mark_processed(conn, msg_key):
  with conn:
    conn.execute(
      "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)", (msg_key,)
    )


def assign_runway(conn, airport_id, aircraft_id, new_status="LANDING_ASSIGNED"):
    with conn:
        # 1. Re-entrancy check: return existing assignment if aircraft already holds one
        row = conn.execute(
            HQC[16],
            (airport_id, aircraft_id)
        ).fetchone()

        if row is not None:
            runway_id = row[0]
            conn.execute(
                HQC[17],
                (new_status, airport_id, aircraft_id)
            )
            return runway_id

        # 2. Pick lowest runway_id that is 'Available' in `runways` AND free in `runway_assignments`
        row = conn.execute( HQC[13],(airport_id,)).fetchone()

        if row is None:
            return None

        runway_id = row[0]

        # 3. Insert assignment
        conn.execute(
           HQC[15], (airport_id, runway_id, aircraft_id, new_status, now())
        )

    return runway_id

def free_runway(conn, airport_id, aircraft_id):
    with conn:
        row = conn.execute(
            HQC[16],
            (airport_id, aircraft_id)
        ).fetchone()
        if row is None:
            return None
        runway_id = row[0]

        conn.execute(
            HQC[18],
            (airport_id, aircraft_id)
        )
    return runway_id