"""REQ-OPS-006: read-only coordinate telemetry and explicit departure reports."""

import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from src.command import aircraft, dashboard
from src.tower.messaging import db


@pytest.fixture
def radar_database(tmp_path, monkeypatch):
    path = tmp_path / "radar.db"
    with sqlite3.connect(path) as conn:
        # No runway_id column: both versions of Radar's store are supported.
        conn.execute("CREATE TABLE aircraft (aircraft_id TEXT PRIMARY KEY, latitude REAL, longitude REAL, altitude REAL, status TEXT, timestamp TEXT)")
        conn.execute("INSERT INTO aircraft VALUES ('AA123', 40.66, -73.79, 2500, 'Landing', '2026-10-22T15:00:00')")
    monkeypatch.setenv("COMMAND_RADAR_DB", str(path))
    monkeypatch.setattr(db, "DB", str(tmp_path / "messages.db"))
    return path


def test_coordinates_read_without_changing_database(radar_database):
    before = radar_database.read_bytes()
    state = aircraft.get_aircraft_state()
    assert state["aircraft"] == [dict(aircraft_id="AA123", latitude=40.66, longitude=-73.79, altitude=2500,
                                      status="Landing", timestamp="2026-10-22T15:00:00")]
    assert state["observed_at"].endswith("+00:00")
    assert state["lifecycle_available"] is False
    assert radar_database.read_bytes() == before
    assert not radar_database.with_name("messages.db").exists()


def test_empty_database_is_valid(radar_database):
    with sqlite3.connect(radar_database) as conn:
        conn.execute("DELETE FROM aircraft")
    assert aircraft.get_aircraft_state()["aircraft"] == []


@pytest.mark.parametrize("latitude,longitude", [(91, 0), (-91, 0), (0, 181), (0, -181), (None, 0), (0, "bad"), (float("inf"), 0)])
def test_invalid_coordinates_omitted_without_breaking_snapshot(radar_database, latitude, longitude):
    with sqlite3.connect(radar_database) as conn:
        conn.execute("INSERT INTO aircraft VALUES ('BAD', ?, ?, 10, 'Landing', 'time')", (latitude, longitude))
    state = aircraft.get_aircraft_state()
    assert len(state["aircraft"]) == 1
    assert state["invalid_coordinate_count"] == 1
    json.dumps(state, allow_nan=False)


def test_unknown_altitude_is_not_misrepresented_as_zero(radar_database):
    with sqlite3.connect(radar_database) as conn:
        conn.execute("UPDATE aircraft SET altitude = ?", (float("inf"),))
    assert aircraft.get_aircraft_state()["aircraft"][0]["altitude"] is None


def test_explicit_departure_hides_retained_row_without_consuming_messages(radar_database):
    db.init_db()
    db.save_message("radar", "tower-READ", json.dumps({"type": "DEPARTED", "aircraft_id": "AA123"}))
    db.save_message("radar", "tower", "not JSON")
    db.save_message("radar", "tower", "[]")
    db.save_message("radar", "tower", '{"aircraft_id": []}')
    before = radar_database.with_name("messages.db").read_bytes()
    state = aircraft.get_aircraft_state()
    assert state["aircraft"] == []
    assert state["departed_count"] == 1
    assert state["lifecycle_available"] is True
    assert radar_database.with_name("messages.db").read_bytes() == before
    with sqlite3.connect(radar_database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM aircraft").fetchone()[0] == 1


@pytest.mark.parametrize("payload", [
    {"type": "REQUEST_LANDING", "aircraft_id": "AA123"},
    {"type": "REQUEST_TAKEOFF", "aircraft_id": "AA123"},
    {"aircraft_id": "AA123", "latitude": 40.66, "longitude": -73.79},
])
def test_later_radar_event_reactivates_aircraft(radar_database, payload):
    db.init_db()
    db.save_message("radar", "tower", json.dumps({"type": "DEPARTED", "aircraft_id": "AA123"}))
    db.save_message("radar", "tower", json.dumps(payload))
    assert len(aircraft.get_aircraft_state()["aircraft"]) == 1


def test_tower_assignment_absence_does_not_hide_aircraft(radar_database, tower_database):
    db.init_db()
    db.save_message("tower", "radar", json.dumps({"type": "DEPARTED", "aircraft_id": "AA123"}))
    assert len(aircraft.get_aircraft_state()["aircraft"]) == 1


def test_default_path_is_checkout_relative(radar_database, monkeypatch, tmp_path):
    monkeypatch.delenv("COMMAND_RADAR_DB")
    monkeypatch.setattr(aircraft, "REPOSITORY_ROOT", tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert len(aircraft.get_aircraft_state()["aircraft"]) == 1


def test_aircraft_endpoint_and_independent_missing_radar(radar_database, tower_database, monkeypatch, tmp_path):
    with TestClient(dashboard.app) as client:
        assert client.get("/api/aircraft").json()["aircraft"][0]["aircraft_id"] == "AA123"
        missing = tmp_path / "missing.db"
        monkeypatch.setenv("COMMAND_RADAR_DB", str(missing))
        response = client.get("/api/aircraft")
        assert response.status_code == 503
        assert str(missing) not in response.text
        assert not missing.exists()
        assert client.get("/api/airport").status_code == 200
        assert client.get("/api/command-messages").status_code == 200


def test_real_radar_to_tower_to_command_flow(tmp_path, monkeypatch):
    """Exercise the current teams' actual schemas and message producers."""
    from src.radar.airplane.aircraft_repo import init_db as init_radar, update_altitude
    from src.radar.airplane.create_airplane import create_airplane
    from src.radar.airplane.runway_requests import request_landing, report_departed, send_aircraft_info
    from src.tower.airport.airport_repo import create_tables, create_airport
    from src.tower.airport.runway_requests import answer_requests

    radar_path, tower_path = tmp_path / "radar.db", tmp_path / "tower.db"
    monkeypatch.setenv("COMMAND_RADAR_DB", str(radar_path))
    monkeypatch.setenv("COMMAND_TOWER_DB", str(tower_path))
    monkeypatch.setenv("COMMAND_AIRPORT_ID", "DEMO-001")
    monkeypatch.setattr(db, "DB", str(tmp_path / "messages.db"))
    radar = init_radar(str(radar_path))
    tower = sqlite3.connect(tower_path)
    try:
        assert create_tables(tower)
        assert create_airport(tower, "DEMO-001", 21000, 40.6413, -73.7781)
        create_airplane(radar, "FLOW01", 40.67, -73.82, 3500, "Landing")
        with TestClient(dashboard.app) as client:
            # A position is visible even before Tower assigns a runway.
            assert client.get("/api/aircraft").json()["aircraft"][0]["latitude"] == 40.67
            assert not any(row["aircraft_id"] for row in client.get("/api/airport").json()["runways"])
            request_landing(radar, "FLOW01")
            answer_requests(tower, "DEMO-001")
            assigned = [row for row in client.get("/api/airport").json()["runways"] if row["aircraft_id"] == "FLOW01"]
            assert len(assigned) == 1
            assert assigned[0]["status"] == "Not Available"
            assert client.get("/api/aircraft").json()["aircraft"][0]["altitude"] == 3500
            update_altitude(radar, "FLOW01", 2750)
            assert client.get("/api/aircraft").json()["aircraft"][0]["altitude"] == 2750
            report_departed(radar, "FLOW01")
            answer_requests(tower, "DEMO-001")
            assert client.get("/api/aircraft").json()["aircraft"] == []
            assert not any(row["aircraft_id"] for row in client.get("/api/airport").json()["runways"])
            send_aircraft_info(radar, "FLOW01")
            assert client.get("/api/aircraft").json()["aircraft"] == []
    finally:
        radar.close()
        tower.close()
