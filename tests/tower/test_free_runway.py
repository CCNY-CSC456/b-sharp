# REQ-TOW-010
# Automated tests for Free Runway. CI runs these with: pytest tests/tower

import sqlite3
from datetime import datetime

from src.tower.airport.airport_repo import TIME_FORMAT, assign_runway, create_airport, create_tables, free_runway


def new_airport():
    conn = sqlite3.connect(":memory:")  # a throwaway database that only lives in RAM
    create_tables(conn)
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    return conn


################################################################################
# def runway(conn, runway_id):
#     """Return ("Not Available", aircraft_id) if assigned, else ("Available", None)."""
#     row = conn.execute(
#         "SELECT aircraft_id FROM runway_assignments WHERE airport_id = 'JFK' AND runway_id = ?",
#         (runway_id,)
#     ).fetchone()
#
#     if row is None:
#         return ("Available", None)
#     return ("Not Available", row[0])
def runway(conn, runway_id):
    # 1. Is the runway physically closed/out of service?
    r_row = conn.execute(
        "SELECT status FROM runways WHERE airport_id = 'JFK' AND runway_id = ?",
        (runway_id,)
    ).fetchone()
    if r_row and r_row[0] == "Not Available":
        return ("Not Available", None, None)

    # 2. Is there an active aircraft assignment on this runway?
    ra_row = conn.execute(
        "SELECT aircraft_id, assigned_at FROM runway_assignments WHERE airport_id = 'JFK' AND runway_id = ?",
        (runway_id,)
    ).fetchone()
    if ra_row is not None:
        return ("Not Available", ra_row[0], ra_row[1])

    # 3. Otherwise, it is open and unassigned
    return ("Available", None, None)
################################################################################


def test_free_makes_the_runway_available_again():
    conn = new_airport()
    assign_runway(conn, "JFK", "AA123")
    assert free_runway(conn, "JFK", "AA123") == 1
    status, aircraft_id, timestamp = runway(conn, 1)
    assert status == "Available"
    assert aircraft_id is None
    datetime.strptime(timestamp, TIME_FORMAT)  # raises if the format is wrong


def test_free_only_changes_that_airplanes_runway():
    conn = new_airport()
    assign_runway(conn, "JFK", "AA123")  # runway 1
    assign_runway(conn, "JFK", "UA456")  # runway 2
    free_runway(conn, "JFK", "AA123")
    assert runway(conn, 2)[:2] == ("Not Available", "UA456")


def test_freeing_twice_changes_nothing():
    conn = new_airport()
    assign_runway(conn, "JFK", "AA123")
    free_runway(conn, "JFK", "AA123")
    assert free_runway(conn, "JFK", "AA123") is None


def test_free_airplane_without_a_runway():
    conn = new_airport()
    assert free_runway(conn, "JFK", "AA123") is None
    taken = conn.execute("SELECT COUNT(*) FROM runways WHERE status = 'Not Available'").fetchone()
    assert taken == (0,)


def test_free_at_unknown_airport():
    conn = new_airport()
    assign_runway(conn, "JFK", "AA123")
    assert free_runway(conn, "LGA", "AA123") is None
    assert runway(conn, 1)[:2] == ("Not Available", "AA123")  # JFK's runway is untouched


def test_freed_runway_can_be_assigned_again():
    conn = new_airport()
    for n in range(1, 11):
        assign_runway(conn, "JFK", f"PLANE{n}")
    assert assign_runway(conn, "JFK", "LATE1") is None  # all 10 taken
    assert free_runway(conn, "JFK", "PLANE3") == 3
    assert assign_runway(conn, "JFK", "LATE1") == 3     # the freed runway goes to the next plane
