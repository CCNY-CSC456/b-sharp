# REQ-TOW-006
# Automated tests for Create Airport. CI runs these with: pytest tests/tower

import sqlite3
from datetime import datetime

import pytest
from src.tower.airport.airport_repo import TIME_FORMAT, create_airport, create_tables


def new_db():
    conn = sqlite3.connect(":memory:")  # a throwaway database that only lives in RAM
    create_tables(conn)
    return conn


def test_create_tables():
    conn = sqlite3.connect(":memory:")
    assert create_tables(conn) is True
    assert create_tables(conn) is True  # safe to call again


def test_create_airport_saves_the_airport():
    conn = new_db()
    assert create_airport(conn, "JFK", 21000, 40.6413, -73.7781) is True
    rows = conn.execute("SELECT * FROM airport").fetchall()
    assert rows == [("JFK", 21000.0, 40.6413, -73.7781)]


def test_airport_has_10_available_runways():
    conn = new_db()
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    rows = conn.execute("SELECT runway_id, status, timestamp FROM runways WHERE airport_id = 'JFK'").fetchall()
    assert [runway_id for runway_id, _, _ in rows] == list(range(1, 11))
    assert all(status == "Available" for _, status, _ in rows)
    for _, _, timestamp in rows:
        datetime.strptime(timestamp, TIME_FORMAT)  # raises if the format is wrong


def test_duplicate_airport_rejected():
    conn = new_db()
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    assert create_airport(conn, "JFK", 21000, 40.6413, -73.7781) is False
    assert conn.execute("SELECT COUNT(*) FROM runways").fetchone() == (10,)  # no extra runways added


def test_invalid_runway_status_rejected():
    conn = new_db()
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE runways SET status = 'Closed' WHERE runway_id = 1")


def test_create_tables_returns_false_on_error():
    conn = sqlite3.connect(":memory:")
    conn.close()  # a closed connection can't create anything
    assert create_tables(conn) is False
