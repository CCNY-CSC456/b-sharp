"""REQ-OPS-001 / REQ-OPS-005: read actual Tower state without mutating it."""

from datetime import datetime, timezone
import sqlite3

import pytest

from src.command import airport


def test_reads_legacy_tower_data_without_inventing_an_aircraft_phase(tower_database):
    with sqlite3.connect(tower_database) as conn:
        conn.execute("UPDATE runways SET status='Not Available', aircraft_id='AA123' WHERE runway_id=2")
    state = airport.get_airport_state()
    assert state["airport_id"] == "DEMO-001"
    assert state["perimeter"] == 21000
    assert state["latitude"] == 40.6413
    assert state["number_of_runways"] == 10
    assert [r["runway_id"] for r in state["runways"]] == list(range(1, 11))
    assert state["assignment_source"] == "legacy_runways"
    assert state["runways"][1]["aircraft_id"] == "AA123"
    assert state["runways"][1]["assignment_status"] is None
    assert state["runways"][1]["status"] == "Not Available"
    assert datetime.fromisoformat(state["observed_at"]).tzinfo == timezone.utc


def test_assignments_override_legacy_aircraft_but_preserve_base_availability(assignments_database):
    with sqlite3.connect(assignments_database) as conn:
        conn.execute("UPDATE runways SET status='Not Available', aircraft_id='OLD' WHERE runway_id=1")
    before = assignments_database.read_bytes()
    state = airport.get_airport_state()
    assert assignments_database.read_bytes() == before
    assert state["assignment_source"] == "runway_assignments"
    assert state["runways"][0]["aircraft_id"] is None
    assert state["runways"][0]["status"] == "Not Available"
    assigned = state["runways"][1]
    assert assigned["status"] == "Not Available"
    assert assigned["aircraft_id"] == "AA123"
    assert assigned["assignment_status"] == "LANDING_ASSIGNED"
    assert assigned["assigned_at"] == "2026-10-22T15:00:00"
    assert assigned["timestamp"] == "2026-10-22T14:00:00"


def test_unavailable_runway_stays_unavailable_with_an_empty_assignments_table(assignments_database):
    with sqlite3.connect(assignments_database) as conn:
        conn.execute("DELETE FROM runway_assignments")
        conn.execute("UPDATE runways SET status='Not Available' WHERE runway_id=1")
    state = airport.get_airport_state()
    assert state["runways"][0]["status"] == "Not Available"
    assert state["runways"][0]["aircraft_id"] is None
    assert sum(r["status"] == "Available" for r in state["runways"]) == 9


@pytest.mark.parametrize("status", ["LANDED", "TAKEOFF_ASSIGNED"])
def test_later_status_changes_are_visible_on_next_read(assignments_database, status):
    airport.get_airport_state()
    with sqlite3.connect(assignments_database) as conn:
        conn.execute("UPDATE runway_assignments SET status=?", (status,))
    assert airport.get_airport_state()["runways"][1]["assignment_status"] == status


def test_departure_removes_aircraft_and_empty_table_is_a_valid_snapshot(assignments_database):
    assert airport.get_airport_state()["runways"][1]["aircraft_id"] == "AA123"
    with sqlite3.connect(assignments_database) as conn:
        conn.execute("DELETE FROM runway_assignments")
    state = airport.get_airport_state()
    assert len(state["runways"]) == 10
    assert all(r["aircraft_id"] is None and r["status"] == "Available" for r in state["runways"])


def test_airports_are_filtered_on_both_tables(assignments_database, monkeypatch):
    with sqlite3.connect(assignments_database) as conn:
        conn.execute("INSERT INTO airport VALUES ('OTHER', 100, -10, 20)")
        conn.execute("INSERT INTO runways VALUES ('OTHER', 7, 'Available', '2026-10-22T14:00:00', NULL)")
        conn.execute("INSERT INTO runway_assignments VALUES ('OTHER', 7, 'OTHER123', 'LANDED', '2026-10-22T15:00:00')")
    assert not any(r["aircraft_id"] == "OTHER123" for r in airport.get_airport_state()["runways"])
    monkeypatch.setenv("COMMAND_AIRPORT_ID", "OTHER")
    state = airport.get_airport_state()
    assert state["perimeter"] == 100
    assert state["number_of_runways"] == 1
    assert state["runways"][0]["aircraft_id"] == "OTHER123"


def test_missing_database_is_not_created(tmp_path, monkeypatch):
    path = tmp_path / "not-created.db"
    monkeypatch.setenv("COMMAND_TOWER_DB", str(path))
    with pytest.raises(sqlite3.OperationalError):
        airport.get_airport_state()
    assert not path.exists()


def test_unknown_airport_does_not_return_demo_data(tower_database, monkeypatch):
    monkeypatch.setenv("COMMAND_AIRPORT_ID", "MISSING")
    with pytest.raises(sqlite3.OperationalError):
        airport.get_airport_state()


def test_default_path_is_checkout_root_even_from_a_different_directory(tower_database, monkeypatch, tmp_path):
    monkeypatch.delenv("COMMAND_TOWER_DB")
    monkeypatch.setattr(airport, "REPOSITORY_ROOT", tower_database.parent)
    other = tmp_path / "other-directory"
    other.mkdir()
    monkeypatch.chdir(other)
    assert airport.get_airport_state()["airport_id"] == "DEMO-001"


def test_real_current_tower_schema_is_readable(tmp_path, monkeypatch):
    from src.tower.airport.airport_repo import create_airport, create_tables, assign_runway
    path = tmp_path / "actual-tower.db"
    with sqlite3.connect(path) as conn:
        assert create_tables(conn)
        assert create_airport(conn, "DEMO-001", 21000, 40.6413, -73.7781)
        assign_runway(conn, "DEMO-001", "REAL123")
    monkeypatch.setenv("COMMAND_TOWER_DB", str(path))
    assert airport.get_airport_state()["runways"][0]["aircraft_id"] == "REAL123"
