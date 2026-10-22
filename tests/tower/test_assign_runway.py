# REQ-TOW-007
# Automated tests for Assign Runway. CI runs these with: pytest tests/tower

import sqlite3
from datetime import datetime

from src.tower.airport.airport_repo import TIME_FORMAT, assign_runway, create_airport, create_tables


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

# def runway(conn, runway_id):
#     # 1. Is the runway physically closed/out of service?
#     r_row = conn.execute(
#         "SELECT status FROM runways WHERE airport_id = 'JFK' AND runway_id = ?",
#         (runway_id,)
#     ).fetchone()
#     if r_row and r_row[0] == "Not Available":
#         return ("Not Available", None, None)
#
#     # 2. Is there an active aircraft assignment on this runway?
#     ra_row = conn.execute(
#         "SELECT aircraft_id, assigned_at FROM runway_assignments WHERE airport_id = 'JFK' AND runway_id = ?",
#         (runway_id,)
#     ).fetchone()
#     if ra_row is not None:
#         return ("Not Available", ra_row[0], ra_row[1])
#
#     # 3. Otherwise, it is open and unassigned
#     return ("Available", None, None)
################################################################################


def test_new_runways_have_no_airplane(runway):
    conn = new_airport()
    assert runway(conn, 1)[1] is None


def test_assign_gives_runway_1_and_marks_it_taken(runway):
    conn = new_airport()
    assert assign_runway(conn, "JFK", "AA123") == 1
    status, aircraft_id, timestamp = runway(conn, 1)
    assert status == "Not Available"
    assert aircraft_id == "AA123"
    datetime.strptime(timestamp, TIME_FORMAT)  # raises if the format is wrong


def test_two_airplanes_get_different_runways():
    conn = new_airport()
    assert assign_runway(conn, "JFK", "AA123") == 1
    assert assign_runway(conn, "JFK", "UA456") == 2


def test_same_airplane_gets_the_same_runway_again():
    conn = new_airport()
    assert assign_runway(conn, "JFK", "AA123") == 1
    assert assign_runway(conn, "JFK", "AA123") == 1  # asking again doesn't take a second runway
    taken = conn.execute("SELECT COUNT(*) FROM runway_assignments WHERE airport_id = 'JFK'").fetchone()
    assert taken == (1,)


def test_skips_runways_that_are_not_available():
    conn = new_airport()
    conn.execute("UPDATE runways SET status = 'Not Available' WHERE runway_id = 1")
    assert assign_runway(conn, "JFK", "AA123") == 2


def test_no_runway_when_all_are_taken():
    conn = new_airport()
    for n in range(1, 11):
        assert assign_runway(conn, "JFK", f"PLANE{n}") == n
    assert assign_runway(conn, "JFK", "LATE1") is None  # all 10 taken


def test_no_runway_for_unknown_airport():
    conn = new_airport()
    assert assign_runway(conn, "LGA", "AA123") is None
