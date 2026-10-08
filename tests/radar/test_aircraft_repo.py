# REQ-RAD-012
# Automated tests for Create Airplane. CI runs these with: pytest tests/radar

from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, init_db
from src.radar.airplane.create_airplane import create_airplane, send_to_tower
from src.radar.airplane.models import AircraftTelemetry
from src.tower.messaging import db as tower_db


def make_plane(status="Parked"):
    return AircraftTelemetry(
        aircraft_id="AA123",
        latitude=40.7769,
        longitude=-73.8740,
        altitude=0,
        status=status,
        timestamp=datetime(2026, 1, 1, 12, 0, 0),
    )


def test_create_saves_the_plane():
    conn = init_db(":memory:")  # a throwaway database that only lives in RAM
    create_aircraft(conn, make_plane())
    rows = conn.execute("SELECT * FROM aircraft").fetchall()
    assert rows == [("AA123", 40.7769, -73.8740, 0.0, "Parked", "2026-01-01T12:00:00")]


def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        make_plane(status="Flying")


def test_duplicate_id_rejected():
    conn = init_db(":memory:")
    create_aircraft(conn, make_plane())
    with pytest.raises(ValueError):
        create_aircraft(conn, make_plane())


def test_create_airplane_sends_the_plane():
    conn = init_db(":memory:")
    sent = []  # a fake "messaging service" that just remembers what it was given
    plane = create_airplane(conn, "AA123", 40.7769, -73.8740, 0, "Parked", send=sent.append)
    assert sent == [plane]


def test_send_to_tower(tmp_path, monkeypatch):
    # Point tower's database at a throwaway file so we never touch the real messages.db
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    send_to_tower(make_plane())
    inbox = tower_db.get_messages("tower")
    assert inbox[0]["sender"] == "radar"
    assert "AA123" in inbox[0]["content"]
