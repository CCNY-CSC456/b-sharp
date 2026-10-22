"""Command-owned fixtures for the two Tower database contracts."""

import sqlite3

import pytest


@pytest.fixture
def tower_database(tmp_path, monkeypatch):
    path = tmp_path / "tower.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE airport (airport_id TEXT PRIMARY KEY, perimeter REAL, latitude REAL, longitude REAL);
            CREATE TABLE runways (
                airport_id TEXT, runway_id INTEGER, status TEXT, timestamp TEXT, aircraft_id TEXT,
                PRIMARY KEY (airport_id, runway_id)
            );
            INSERT INTO airport VALUES ('DEMO-001', 21000, 40.6413, -73.7781);
        """)
        conn.executemany(
            "INSERT INTO runways VALUES ('DEMO-001', ?, 'Available', '2026-10-22T14:00:00', NULL)",
            [(i,) for i in range(1, 11)],
        )
    monkeypatch.setenv("COMMAND_TOWER_DB", str(path))
    monkeypatch.setenv("COMMAND_AIRPORT_ID", "DEMO-001")
    return path


@pytest.fixture
def assignments_database(tower_database):
    # The agreed message_reform contract; tests do not modify Tower's source.
    with sqlite3.connect(tower_database) as conn:
        conn.execute("""
            CREATE TABLE runway_assignments (
                airport_id TEXT NOT NULL, runway_id INTEGER NOT NULL UNIQUE,
                aircraft_id TEXT NOT NULL UNIQUE,
                status TEXT CHECK(status IN ('LANDING_ASSIGNED', 'LANDED', 'TAKEOFF_ASSIGNED')),
                assigned_at TEXT NOT NULL, PRIMARY KEY (airport_id, runway_id)
            )
        """)
        conn.execute(
            "INSERT INTO runway_assignments VALUES ('DEMO-001', 2, 'AA123', 'LANDING_ASSIGNED', '2026-10-22T15:00:00')"
        )
    return tower_database
