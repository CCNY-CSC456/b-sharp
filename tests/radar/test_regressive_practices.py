##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

# fresh new slop

# from src.radar.airplane.regressive_mocking import fake_unsafe_separation as fake_separation
# import src.radar.airplane.regressive_mocking as MOCK

### from test_set_position

# REQ-RAD-020
# Automated tests for changing a plane's position by hand. CI runs these with: pytest tests/radar
# Imagine testing this by hand in 12026 HE

import json
from datetime import datetime

import argparse # HACK

import pytest

from src.radar.airplane import fake_cli as fcli
from src.radar.airplane.aircraft_repo import (
  create_aircraft,
  get_aircraft,
  init_db,
  update_position
)
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

SHITTEST_PLANE_MACRO = AircraftTelemetry(
                        aircraft_id="AA123",
                        latitude=40.0,
                        longitude=70.0,
                        altitude=3000,
                        status="Landing",
                        timestamp=OLD_TIME,
                      )

def SHITTY_SETUP():
    conn = init_db(":memory:")
    create_aircraft(
      conn,
      AircraftTelemetry(
        aircraft_id="AA123",
        latitude=40.0,
        longitude=70.0,
        altitude=3000,
        status="Landing",
        timestamp=OLD_TIME
      )
    )
    return conn


def SHITTY_TYPE_ANSWERS(monkeypatch, answers):
    answers = iter(answers)
    monkeypatch.setattr("builtins.input", lambda question: next(answers))

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->
### from test_monitor

import json
import time
from datetime import datetime, timedelta

from src.radar.airplane import __main__ as cli
from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db
from src.radar.airplane.conflicts import get_conflicts, open_conflict
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.monitor import run, tick
from src.tower.messaging import db as tower_db

MEM = ":memory:"
OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)
T0 = datetime(2026, 11, 19, 14, 0, 0)

SHIT_REPORT = argparse.Namespace (
  command="report-conflict",
  json_payload=None,
  interactive=True,
  aircraft_id=None,
  pos_aircraft_id=None,
  reason=None,
  pos_reason=None,
)

MINI_SHIT = argparse.Namespace(commands="conflicts")

SHIT_THING_ONE = argparse.Namespace(
    command="fake-unsafe-separation",
    json_payload=None,
    interactive=True,
    aircraft_id=None,
    pos_aircraft_id=None,
    latitude=None,
    pos_latitude=None,
    longitude=None,
    pos_longitude=None,
)

SHIT_THING_TWO = argparse.Namespace(
    command="set-position",
    json_payload=None,
    interactive=True,
    aircraft_id=None,
    conflict_id=None,
    pos_conflict_id=None,
)

def SHITTY_PLANE_MACRO(aircraft_id, status="Landing", latitude=40.7):
    return AircraftTelemetry(
      aircraft_id=aircraft_id,
      latitude=latitude,
      longitude=-73.8,
      altitude=3000,
      status=status,
      timestamp=OLD_TIME
    )

def SHITTIER_TYPE_ANSWERS(monkeypatch, answers):
    answers = iter(answers)
    monkeypatch.setattr("builtins.input", lambda question: next(answers))

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

### from test_set_position
def test_set_position_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = SHITTY_SETUP()
    SHITTY_TYPE_ANSWERS(monkeypatch, ["AA123", "north", "40.5", "-73.25"])   # "north" isn't a number, asked again
    cli.cmd_set_position(conn, COMPATIBILITY_COMPROMISE)
    plane = get_aircraft(conn, "AA123")
    assert (plane.latitude, plane.longitude) == (40.5, -73.25)
    assert plane.timestamp > OLD_TIME
    assert "Moved AA123 to (40.5, -73.25) and sent the update to tower." in capsys.readouterr().out
    sent = json.loads(tower_db.get_messages("tower")[0]["content"])
    assert sent["type"] == "AIRCRAFT_INFO"
    assert (sent["latitude"], sent["longitude"]) == (40.5, -73.25)



def test_set_position_command_bad_input(tmp_path, monkeypatch):
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = SHITTY_SETUP()

    SHITTY_TYPE_ANSWERS(monkeypatch, ["NOPE", "40", "70"])
    with pytest.raises(ValueError, match="aircraft NOPE does not exist"):
        cli.cmd_set_position(conn, COMPATIBILITY_COMPROMISE)

    SHITTY_TYPE_ANSWERS(monkeypatch, ["AA123", "100", "70"])
    with pytest.raises(ValueError, match="latitude must be between -90 and 90"):
        cli.cmd_set_position(conn, COMPATIBILITY_COMPROMISE)

    tower_db.init_db()
    assert tower_db.get_messages("tower") == []

# alt versions driving cli (?) uh that's not the right phrasing

def test_set_position_command_alt(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "radar.db"
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))

    conn = init_db(str(db_path))
    create_aircraft(conn, SHITTEST_PLANE_MACRO, )
    conn.close()

    cli.main(["--db", str(db_path), "set-position", "AA123", "40.5", "-73.25"])

    check_conn = init_db(str(db_path))
    plane = get_aircraft(check_conn, "AA123")
    check_conn.close()

    assert (plane.latitude, plane.longitude) == (40.5, -73.25)
    assert plane.timestamp > OLD_TIME #OLD_TIME.isoformat()
    assert "Moved AA123 to (40.5, -73.25) and sent the update to tower." in capsys.readouterr().out

    sent = json.loads(tower_db.get_messages("tower")[0]["content"])
    assert sent["type"] == "AIRCRAFT_INFO"
    assert (sent["latitude"], sent["longitude"]) == (40.5, -73.25)


def test_set_position_command_bad_inputalt(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "radar.db"
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))

    conn = init_db(str(db_path))
    create_aircraft(conn, SHITTEST_PLANE_MACRO, )
    conn.close()

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--db", str(db_path), "set-position", "NOPE", "40", "70"])
    assert exc_info.value.code == 1
    assert "aircraft NOPE does not exist" in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--db", str(db_path), "set-position", "AA123", "100", "70"])
    assert exc_info.value.code == 1
    assert "latitude must be between -90 and 90" in capsys.readouterr().out

    tower_db.init_db()
    assert tower_db.get_messages("tower") == []

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

### from test_monitor

# --- the menu commands ---




def test_report_conflict_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(MEM)
    create_aircraft(conn, SHITTY_PLANE_MACRO("AA123"))
    SHITTIER_TYPE_ANSWERS(monkeypatch, ["AA123", "low on gas", "3"])   # a bad choice is asked again
    cli.cmd_report_conflict(conn, SHIT_REPORT)
    out = capsys.readouterr().out
    assert "Conflict LOW_FUEL opened for AA123" in out
    assert get_conflicts(conn)[0]["reason"] == "LOW_FUEL"


def test_report_conflict_command_unknown_plane(monkeypatch, capsys):
    conn = init_db(MEM)

    SHITTIER_TYPE_ANSWERS(monkeypatch, ["NOPE", "1"])
    with pytest.raises(ValueError, match="aircraft NOPE does not exist"):
      cli.cmd_report_conflict(conn, SHIT_REPORT)



def test_conflicts_command(capsys):
    conn = init_db(MEM)
    cli.cmd_conflicts(conn, MINI_SHIT)
    assert "No conflicts" in capsys.readouterr().out
    create_aircraft(conn, SHITTY_PLANE_MACRO("AA123"))
    open_conflict(conn, "AA123", "LATE_4H", clock=lambda: T0)
    cli.cmd_conflicts(conn, MINI_SHIT)
    out = capsys.readouterr().out
    assert "AA123" in out and "LATE_4H" in out and "OPEN" in out


def test_fake_tower_commands_round_trip(tmp_path, monkeypatch, capsys):
    # The testing helpers put tower-shaped messages in radar's real inbox, which a tick then reads.
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(MEM)
    create_aircraft(conn, SHITTY_PLANE_MACRO("AA123"))
    SHITTIER_TYPE_ANSWERS(monkeypatch, ["AA123", "41.0", "-74.0"])
    fcli.cmd_fake_unsafe_separation(conn, SHIT_THING_ONE)
    conflict = open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: T0)
    SHITTIER_TYPE_ANSWERS(monkeypatch, [conflict["conflict_id"]])
    fcli.cmd_fake_conflict_resolved(conn, SHIT_THING_TWO)
    from src.radar.airplane.runway_requests import read_radar_inbox, send_to_tower
    tick(conn, get=read_radar_inbox, send=send_to_tower, clock=lambda: T0)
    assert get_aircraft(conn, "AA123").latitude == 41.0
    assert get_conflicts(conn)[0]["status"] == "RESOLVED"




def test_run_stops_cleanly_on_ctrl_c():
    conn = init_db(MEM)
    lines = []

    def sleep(seconds):
        raise KeyboardInterrupt

    run(conn, get=lambda: [], send=lambda raw: None, clock=lambda: T0, sleep=sleep, out=lines.append)
    assert lines[-1] == "Radar stopped."

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->