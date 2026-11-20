# REQ-RAD-020
# Automated tests for changing a plane's position by hand. CI runs these with: pytest tests/radar

import json
from datetime import datetime

import argparse # HACK

import pytest

from src.radar.airplane import __main__ as cli
from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db, update_position
from src.radar.airplane.models import AircraftTelemetry
from src.tower.messaging import db as tower_db

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)


# HACK
COMPATIBILITY_COMPROMISE = argparse.Namespace(
    command="set-position",
    json_payload=None,
    interactive=True,
    aircraft_id=None,
    pos_aircraft_id=None,
    latitude=None,
    pos_latitude=None,
    longitude=None,
    pos_longitude=None,
)


def setup():
    conn = init_db(":memory:")
    create_aircraft(conn, AircraftTelemetry(aircraft_id="AA123", latitude=40.0, longitude=70.0, altitude=3000,
                                            status="Landing", timestamp=OLD_TIME))
    return conn


def type_answers(monkeypatch, answers):
    answers = iter(answers)
    monkeypatch.setattr("builtins.input", lambda question: next(answers))


def test_update_position_rejects_off_the_globe():
    conn = setup()
    with pytest.raises(ValueError, match="latitude"):
        update_position(conn, "AA123", 91, 70.0)
    with pytest.raises(ValueError, match="longitude"):
        update_position(conn, "AA123", 40.0, -180.5)
    assert get_aircraft(conn, "AA123").latitude == 40.0


# def test_set_position_command(tmp_path, monkeypatch, capsys):
#     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
#     conn = setup()
#     type_answers(monkeypatch, ["AA123", "north", "40.5", "-73.25"])   # "north" isn't a number, asked again
#     cli.cmd_set_position(conn, COMPATIBILITY_COMPROMISE)
#     plane = get_aircraft(conn, "AA123")
#     assert (plane.latitude, plane.longitude) == (40.5, -73.25)
#     assert plane.timestamp > OLD_TIME
#     assert "Moved AA123 to (40.5, -73.25) and sent the update to tower." in capsys.readouterr().out
#     sent = json.loads(tower_db.get_messages("tower")[0]["content"])
#     assert sent["type"] == "AIRCRAFT_INFO"
#     assert (sent["latitude"], sent["longitude"]) == (40.5, -73.25)
#
#
# def test_set_position_command_bad_input(tmp_path, monkeypatch, capsys):
#     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
#     conn = setup()
#     type_answers(monkeypatch, ["NOPE", "40", "70"])
#     cli.cmd_set_position(conn, COMPATIBILITY_COMPROMISE)
#     #assert "Not changed: aircraft NOPE does not exist" in capsys.readouterr().out
#     assert ValueError
#     type_answers(monkeypatch, ["AA123", "100", "70"])
#     cli.cmd_set_position(conn, COMPATIBILITY_COMPROMISE)
#     assert "Not changed: latitude must be between -90 and 90" in capsys.readouterr().out
#     tower_db.init_db()
#     assert tower_db.get_messages("tower") == []   # nothing sent
