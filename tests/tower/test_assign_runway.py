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
