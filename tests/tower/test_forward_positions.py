# REQ-TOW-009
# Automated tests for forwarding plane positions radar -> tower -> command. CI runs these with: pytest tests/tower
# These use the real messaging service on a throwaway messages.db.

import json
import sqlite3

import pytest

from src.tower.airport import __main__ as cli
from src.tower.airport.airport_repo import create_airport, create_tables
from src.tower.airport.runway_requests import (
    AIRCRAFT_LANDED, AIRCRAFT_PARKED, AIRCRAFT_POSITION, AIRCRAFT_REMOVED, answer_requests, forward_positions,
)
from src.tower.messaging import db as tower_db


@pytest.fixture(autouse=True)
def throwaway_messages(tmp_path, monkeypatch):
    # Point the shared messages.db at a throwaway file so we never touch the real one.
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "messages.db"))
    tower_db.init_db()


@pytest.fixture
def tower():
    conn = sqlite3.connect(":memory:")  # a throwaway tower database that only lives in RAM
    create_tables(conn)
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    return conn


def radar_sends(content):
    tower_db.save_message("radar", "tower", json.dumps(content))


def created(aircraft_id, altitude=2000.0, timestamp="2026-11-15T10:00:00"):
    """The message radar sends when it creates a plane (it has no "type")."""
    return {"aircraft_id": aircraft_id, "latitude": 40.77, "longitude": -73.87, "altitude": altitude,
            "status": "Landing", "timestamp": timestamp, "runway_id": None}


def info(aircraft_id, altitude, timestamp):
    """An AIRCRAFT_INFO update, like radar's set-altitude / send-info."""
    return {**created(aircraft_id, altitude, timestamp), "type": "AIRCRAFT_INFO"}


def command_inbox():
    return [json.loads(m["content"]) for m in tower_db.get_messages("command")]


def test_created_plane_is_forwarded(tower):
    radar_sends(created("A1"))
    forward_positions(tower, "JFK")
    assert command_inbox() == [{
        "type": AIRCRAFT_POSITION, "aircraft_id": "A1", "latitude": 40.77, "longitude": -73.87,
        "altitude": 2000.0, "status": "Landing", "timestamp": "2026-11-15T10:00:00", "runway_id": None,
    }]


def test_altitude_updates_are_forwarded_in_order(tower):
    radar_sends(created("A1"))
    radar_sends(info("A1", 1500.0, "2026-11-15T10:05:00"))
    radar_sends(info("A1", 900.0, "2026-11-15T10:06:00"))
    forward_positions(tower, "JFK")
    assert [m["altitude"] for m in command_inbox()] == [2000.0, 1500.0, 900.0]


def test_position_carries_towers_runway(tower):
    radar_sends(created("A1"))
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "A1", "timestamp": "2026-11-15T10:01:00"})
    answer_requests(tower, "JFK")  # tower assigns runway 1 first
    forward_positions(tower, "JFK")
    assert command_inbox()[-1]["runway_id"] == 1


def test_departed_plane_is_removed(tower):
    radar_sends(created("A1"))
    radar_sends({"type": "REQUEST_TAKEOFF", "aircraft_id": "A1", "timestamp": "2026-11-15T10:01:00"})
    answer_requests(tower, "JFK")
    radar_sends({"type": "DEPARTED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:02:00"})
    answer_requests(tower, "JFK")
    forward_positions(tower, "JFK")
    assert command_inbox()[-1] == {"type": AIRCRAFT_REMOVED, "aircraft_id": "A1", "timestamp": "2026-11-15T10:02:00"}


def test_running_again_sends_nothing_new(tower):
    radar_sends(created("A1"))
    radar_sends({"type": "DEPARTED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:02:00"})
    answer_requests(tower, "JFK")  # tower handles the departure first
    forward_positions(tower, "JFK")
    assert forward_positions(tower, "JFK") == []
    assert len(command_inbox()) == 2


def test_exact_repeat_is_forwarded_once(tower):
    # set-altitude then send-info in the same second send identical messages.
    radar_sends(info("A1", 1200.0, "2026-11-15T10:05:00"))
    radar_sends(info("A1", 1200.0, "2026-11-15T10:05:00"))
    forward_positions(tower, "JFK")
    assert len(command_inbox()) == 1


def test_change_in_the_same_second_is_still_forwarded(tower):
    # Timestamps are to the second: a real change in the same second must not be mistaken for a repeat.
    radar_sends(created("A1", 2000.0, "2026-11-15T10:00:00"))
    radar_sends(info("A1", 1200.0, "2026-11-15T10:00:00"))
    forward_positions(tower, "JFK")
    assert [m["altitude"] for m in command_inbox()] == [2000.0, 1200.0]


def test_update_never_hides_a_runway_request(tower):
    # The request comes first, then a position update, all before tower runs.
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "A1", "timestamp": "2026-11-15T10:01:00"})
    radar_sends(info("A1", 1500.0, "2026-11-15T10:02:00"))
    results = answer_requests(tower, "JFK")
    assert [r["type"] for r in results] == ["RUNWAY_ASSIGNED"]


def test_nothing_goes_to_radar_and_other_messages_are_not_forwarded(tower):
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "A1", "timestamp": "2026-11-15T10:01:00"})
    radar_sends({"type": "LANDED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:03:00"})
    tower_db.save_message("command", "tower", json.dumps(created("X9")))  # not from radar
    tower_db.save_message("radar", "tower", "hello tower")                # not JSON
    assert forward_positions(tower, "JFK") == []
    assert tower_db.get_messages("radar") == []


def test_with_radars_real_code(tower):
    from src.radar.airplane.aircraft_repo import init_db as init_radar_db, update_altitude
    from src.radar.airplane.create_airplane import create_airplane
    from src.radar.airplane.runway_requests import report_departed, send_aircraft_info
    radar = init_radar_db(":memory:")
    create_airplane(radar, "A1", 40.77, -73.87, 2000, "Landing")  # really sends it to tower
    update_altitude(radar, "A1", 900)
    send_aircraft_info(radar, "A1")
    report_departed(radar, "A1")
    answer_requests(tower, "JFK")  # tower handles the departure first
    forward_positions(tower, "JFK")
    sent = command_inbox()
    assert [(m["type"], m.get("altitude")) for m in sent] == [
        (AIRCRAFT_POSITION, 2000.0), (AIRCRAFT_POSITION, 900.0), (AIRCRAFT_REMOVED, None),
    ]


def test_parked_is_forwarded_after_the_runway_is_freed(tower):
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "A1", "timestamp": "2026-11-15T10:01:00"})
    answer_requests(tower, "JFK")
    radar_sends({"type": "PARKED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:10:00"})
    answer_requests(tower, "JFK")  # frees runway 1
    forward_positions(tower, "JFK")
    assert command_inbox()[-1] == {"type": AIRCRAFT_PARKED, "aircraft_id": "A1", "timestamp": "2026-11-15T10:10:00"}


def test_departed_and_parked_wait_until_tower_has_handled_them(tower):
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "A1", "timestamp": "2026-11-15T10:01:00"})
    radar_sends({"type": "REQUEST_TAKEOFF", "aircraft_id": "B2", "timestamp": "2026-11-15T10:01:00"})
    answer_requests(tower, "JFK")
    radar_sends({"type": "PARKED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:10:00"})
    radar_sends({"type": "DEPARTED", "aircraft_id": "B2", "timestamp": "2026-11-15T10:10:00"})
    assert forward_positions(tower, "JFK") == []  # runways not freed yet, so command isn't told yet
    answer_requests(tower, "JFK")                 # now tower frees both runways
    assert [m["type"] for m in forward_positions(tower, "JFK")] == [AIRCRAFT_PARKED, AIRCRAFT_REMOVED]


def test_landed_is_forwarded_after_tower_handles_it(tower):
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "A1", "timestamp": "2026-11-15T10:01:00"})
    answer_requests(tower, "JFK")
    radar_sends({"type": "LANDED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:05:00"})
    assert forward_positions(tower, "JFK") == []  # tower hasn't handled LANDED yet
    answer_requests(tower, "JFK")                 # records the landing (runway kept)
    forward_positions(tower, "JFK")
    assert command_inbox()[-1] == {"type": AIRCRAFT_LANDED, "aircraft_id": "A1", "timestamp": "2026-11-15T10:05:00"}


def test_full_lifecycle_order_for_command(tower):
    radar_sends(created("A1"))
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "A1", "timestamp": "2026-11-15T10:01:00"})
    answer_requests(tower, "JFK"); forward_positions(tower, "JFK")
    radar_sends({"type": "LANDED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:05:00"})
    answer_requests(tower, "JFK"); forward_positions(tower, "JFK")
    radar_sends({"type": "PARKED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:10:00"})
    answer_requests(tower, "JFK"); forward_positions(tower, "JFK")
    radar_sends({"type": "REQUEST_TAKEOFF", "aircraft_id": "A1", "timestamp": "2026-11-15T11:00:00"})
    answer_requests(tower, "JFK"); forward_positions(tower, "JFK")
    radar_sends({"type": "DEPARTED", "aircraft_id": "A1", "timestamp": "2026-11-15T11:05:00"})
    answer_requests(tower, "JFK"); forward_positions(tower, "JFK")
    assert [m["type"] for m in command_inbox()] == [
        AIRCRAFT_POSITION, AIRCRAFT_LANDED, AIRCRAFT_PARKED, AIRCRAFT_REMOVED,
    ]


def test_command_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # tower.db gets created here, not in the repo
    radar_sends(created("A1"))
    monkeypatch.setattr("sys.argv", ["python -m src.tower.airport", "answer-requests"])
    cli.main()
    assert "A1: position sent to command (altitude 2000.0)" in capsys.readouterr().out
    radar_sends({"type": "DEPARTED", "aircraft_id": "A1", "timestamp": "2026-11-15T10:02:00"})
    cli.main()
    assert "A1: told command it departed" in capsys.readouterr().out
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "B2", "timestamp": "2026-11-15T10:03:00"})
    cli.main()
    radar_sends({"type": "PARKED", "aircraft_id": "B2", "timestamp": "2026-11-15T10:04:00"})
    cli.main()
    out = capsys.readouterr().out
    assert "B2: parked, runway 1 freed" in out and "B2: told command it parked" in out
    radar_sends({"type": "REQUEST_LANDING", "aircraft_id": "C3", "timestamp": "2026-11-15T10:05:00"})
    cli.main()
    radar_sends({"type": "LANDED", "aircraft_id": "C3", "timestamp": "2026-11-15T10:06:00"})
    cli.main()
    assert "C3: told command it landed" in capsys.readouterr().out
