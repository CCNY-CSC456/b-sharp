# REQ-RAD-015
# Automated tests for changing an airplane's altitude. CI runs these with: pytest tests/radar

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db, update_altitude
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane import __main__ as cli
from src.tower.messaging import db as tower_db


def make_plane():
    return AircraftTelemetry(
        aircraft_id="AA123",
        latitude=40.7769,
        longitude=-73.8740,
        altitude=0,
        status="Departing",
        timestamp=datetime(2026, 1, 1, 12, 0, 0),
    )


def type_answers(monkeypatch, answers):
    # Pretend a person typed these answers, one per question.
    answers = iter(answers)
    monkeypatch.setattr("builtins.input", lambda question: next(answers))


def test_update_altitude():
    conn = init_db(":memory:")
    create_aircraft(conn, make_plane())
    update_altitude(conn, "AA123", 3000)
    plane = get_aircraft(conn, "AA123")
    assert plane.altitude == 3000.0
    assert plane.timestamp > datetime(2026, 1, 1, 12, 0, 0)  # timestamp was refreshed


def test_update_altitude_unknown_plane():
    conn = init_db(":memory:")
    with pytest.raises(ValueError):
        update_altitude(conn, "NOPE", 3000)


def test_update_altitude_negative_rejected():
    conn = init_db(":memory:")
    create_aircraft(conn, make_plane())
    with pytest.raises(ValueError):
        update_altitude(conn, "AA123", -10)
    assert get_aircraft(conn, "AA123").altitude == 0.0  # nothing changed


def test_set_altitude_command(tmp_path, monkeypatch, capsys):
    # Point tower's database at a throwaway file so we never touch the real messages.db
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(":memory:")
    create_aircraft(conn, make_plane())
    # "high" isn't a number, so the altitude is asked again.
    type_answers(monkeypatch, ["AA123", "high", "3000"])
    cli.set_altitude(conn)
    assert get_aircraft(conn, "AA123").altitude == 3000.0
    assert "Set AA123 altitude to 3000.0 feet and sent the update to tower." in capsys.readouterr().out
    sent = json.loads(tower_db.get_messages("tower")[0]["content"])
    assert sent["type"] == "AIRCRAFT_INFO"
    assert sent["altitude"] == 3000.0


def test_set_altitude_command_unknown_plane(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(":memory:")
    type_answers(monkeypatch, ["NOPE", "3000"])
    cli.set_altitude(conn)
    assert "Not changed" in capsys.readouterr().out
    tower_db.init_db()  # create the empty messages table so we can check it
    assert tower_db.get_messages("tower") == []  # nothing sent
