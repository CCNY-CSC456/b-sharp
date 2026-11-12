
# REQ-RAD-014
# Automated tests for radar telling tower a plane is done with its runway. CI runs these with: pytest tests/radar
# Every test uses an in-memory database and fake messaging, so tower doesn't need to run.

import json
from datetime import datetime

import pytest

from src.radar.airplane.aircraft_repo import create_aircraft, delete_aircraft, get_aircraft, init_db, update_runway
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.runway_requests import check_tower_replies, report_departed, report_landed

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->


from src.radar.airplane.aircraft_repo import create_aircraft, init_db
from src.radar.airplane.create_airplane import create_airplane, send_to_tower
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane import __main__ as cli   # the create / list commands
from src.tower.messaging import db as tower_db



##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->



##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

# NOTE (*4)
OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)
HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_4 = AircraftTelemetry(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=0,
  status="Parked",
  timestamp=OLD_TIME,
)


# NOTE (*3)
HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3 = AircraftTelemetry(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=0,
  status="Parked",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)


# NOTE (*1)
HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_1 = AircraftTelemetry(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=0,
  status="Departing",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)

# NOTE (*2)
HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_2 = AircraftTelemetry(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=3000,
  status="Departing",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

# NOTE (*4)

# --- the report-landed / report-departed menu commands ---

def test_report_commands(tmp_path, monkeypatch, capsys): # TODO purge
    from src.radar.airplane import __main__ as cli
    from src.tower.messaging import db as tower_db
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))  # don't touch the real messages.db
    conn = init_db(":memory:")
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_4)
    monkeypatch.setattr("builtins.input", lambda question: "AA123")
    cli.report(conn, report_landed, "has landed")
    assert "Told tower AA123 has landed." in capsys.readouterr().out
    cli.report(conn, report_departed, "has departed")
    assert "Told tower AA123 has departed." in capsys.readouterr().out
    assert get_aircraft(conn, "AA123") is not None  # the plane is kept
    monkeypatch.setattr("builtins.input", lambda question: "NOPE")
    cli.report(conn, report_departed, "has departed")  # no such plane
    assert "Not sent" in capsys.readouterr().out

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

# NOTE (*3)

def type_answers(monkeypatch, answers):
    # Pretend a person typed these answers, one per question.
    answers = iter(answers)
    monkeypatch.setattr("builtins.input", lambda question: next(answers))


def test_create_command(tmp_path, monkeypatch, capsys): # TODO purge
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(":memory:")
    # "high" isn't a number, so altitude is asked again. "departing" is fine in lowercase.
    type_answers(monkeypatch, ["B46", "40.64", "-73.78", "high", "3000", "departing"])
    cli.create(conn)
    row = conn.execute("SELECT aircraft_id, altitude, status FROM aircraft").fetchone()
    assert row == ("B46", 3000.0, "Departing")
    assert "Created airplane B46" in capsys.readouterr().out
    assert "B46" in tower_db.get_messages("tower")[0]["content"]


def test_create_command_duplicate_id(tmp_path, monkeypatch, capsys): # TODO purge
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(":memory:")
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)  # AA123 already exists
    type_answers(monkeypatch, ["AA123", "0", "0", "0", "Parked"])
    cli.create(conn)
    assert "Not created" in capsys.readouterr().out


def test_list_command(capsys): # TODO purge
    conn = init_db(":memory:")
    cli.show_aircraft(conn)
    assert "No airplanes" in capsys.readouterr().out
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)
    cli.show_aircraft(conn)
    assert "AA123" in capsys.readouterr().out



##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

# NOTE (*1)

def test_set_altitude_command(tmp_path, monkeypatch, capsys): # TODO purge
    # Point tower's database at a throwaway file so we never touch the real messages.db
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(":memory:")
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_1)
    # "high" isn't a number, so the altitude is asked again.
    type_answers(monkeypatch, ["AA123", "high", "3000"])
    cli.set_altitude(conn)
    assert get_aircraft(conn, "AA123").altitude == 3000.0
    assert "Set AA123 altitude to 3000.0 feet and sent the update to tower." in capsys.readouterr().out
    sent = json.loads(tower_db.get_messages("tower")[0]["content"])
    assert sent["type"] == "AIRCRAFT_INFO"
    assert sent["altitude"] == 3000.0


def test_set_altitude_command_unknown_plane(tmp_path, monkeypatch, capsys): # TODO purge
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(":memory:")
    type_answers(monkeypatch, ["NOPE", "3000"])
    cli.set_altitude(conn)
    assert "Not changed" in capsys.readouterr().out
    tower_db.init_db()  # create the empty messages table so we can check it
    assert tower_db.get_messages("tower") == []  # nothing sent


##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->


def test_send_info_command(tmp_path, monkeypatch, capsys): # TODO purge
    # Point tower's database at a throwaway file so we never touch the real messages.db
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(":memory:")
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_2)
    type_answers(monkeypatch, ["AA123"])
    cli.send_info(conn)
    out = capsys.readouterr().out
    assert "Sent AA123 to tower:" in out
    assert "Altitude:  3000.0 ft" in out
    assert "Runway:    -" in out
    assert json.loads(tower_db.get_messages("tower")[0]["content"])["type"] == "AIRCRAFT_INFO"


def test_send_info_command_unknown_plane(monkeypatch, capsys): # TODO purge
    conn = init_db(":memory:")
    type_answers(monkeypatch, ["NOPE"])
    cli.send_info(conn)
    assert "Not sent: aircraft NOPE does not exist" in capsys.readouterr().out

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->
