# REQ-RAD-016
# Automated tests for sending one plane's current data to tower. CI runs these with: pytest tests/radar

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, init_db, update_runway
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.runway_requests import send_aircraft_info
from src.radar.airplane import __main__ as cli
from src.tower.messaging import db as tower_db


def make_plane():
    return AircraftTelemetry(
        aircraft_id="AA123",
        latitude=40.7769,
        longitude=-73.8740,
        altitude=3000,
        status="Departing",
        timestamp=datetime(2026, 1, 1, 12, 0, 0),
    )


def type_answers(monkeypatch, answers):
    # Pretend a person typed these answers, one per question.
    answers = iter(answers)
    monkeypatch.setattr("builtins.input", lambda question: next(answers))


def test_sends_the_plane_data():
    conn = init_db(":memory:")
    create_aircraft(conn, make_plane())
    sent = []  # a fake "messaging service" that just remembers what it was given
    send_aircraft_info(conn, "AA123", send=sent.append)
    assert json.loads(sent[0]) == {
        "type": "AIRCRAFT_INFO",
        "aircraft_id": "AA123",
        "latitude": 40.7769,
        "longitude": -73.8740,
        "altitude": 3000.0,
        "status": "Departing",
        "runway_id": None,
        "timestamp": "2026-01-01T12:00:00",
    }


def test_sends_the_runway_once_assigned():
    conn = init_db(":memory:")
    create_aircraft(conn, make_plane())
    update_runway(conn, "AA123", "R1")
    sent = []
    send_aircraft_info(conn, "AA123", send=sent.append)
    assert json.loads(sent[0])["runway_id"] == "R1"


def test_unknown_plane_sends_nothing():
    conn = init_db(":memory:")
    sent = []
    with pytest.raises(ValueError):
        send_aircraft_info(conn, "NOPE", send=sent.append)
    assert sent == []


def test_send_info_command(tmp_path, monkeypatch, capsys):
    # Point tower's database at a throwaway file so we never touch the real messages.db
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(":memory:")
    create_aircraft(conn, make_plane())
    type_answers(monkeypatch, ["AA123"])
    cli.send_info(conn)
    out = capsys.readouterr().out
    assert "Sent AA123 to tower:" in out
    assert "Altitude:  3000.0 ft" in out
    assert "Runway:    -" in out
    assert json.loads(tower_db.get_messages("tower")[0]["content"])["type"] == "AIRCRAFT_INFO"


def test_send_info_command_unknown_plane(monkeypatch, capsys):
    conn = init_db(":memory:")
    type_answers(monkeypatch, ["NOPE"])
    cli.send_info(conn)
    assert "Not sent: aircraft NOPE does not exist" in capsys.readouterr().out
