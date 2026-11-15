# REQ-TOW-012
# Automated tests for telling command what is on each runway. CI runs these with: pytest tests/tower
# These use the real messaging service on a throwaway messages.db.

import json
import sqlite3

import pytest

from src.tower.airport import __main__ as cli
from src.tower.airport.airport_repo import RUNWAY_COUNT, create_airport, create_tables
from src.tower.airport.runway_requests import AIRCRAFT_LANDED, NO_RUNWAY, answer_requests, forward_positions
from src.tower.airport.runway_status import RUNWAY_STATUS, send_runway_status
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
    send_runway_status(conn, "JFK")  # the first run tells command about every runway
    return conn


def radar_sends(message_type, aircraft_id, timestamp):
    tower_db.save_message("radar", "tower", json.dumps(
        {"type": message_type, "aircraft_id": aircraft_id, "timestamp": timestamp}))


def run_tower(conn):
    """One tower run, in the same order as the terminal command. Returns the RUNWAY_STATUS messages sent."""
    answer_requests(conn, "JFK")
    forward_positions(conn, "JFK")
    return send_runway_status(conn, "JFK")


def command_inbox():
    return [json.loads(m["content"]) for m in tower_db.get_messages("command")]


def what_changed(sent):
    """Just (runway, plane, phase) for each RUNWAY_STATUS, so tests don't depend on the clock."""
    return [(m["runway_id"], m["aircraft_id"], m["phase"]) for m in sent]


def test_first_run_tells_command_every_runway_is_free(tower):
    sent = command_inbox()
    assert len(sent) == RUNWAY_COUNT
    assert what_changed(sent) == [(n, None, None) for n in range(1, RUNWAY_COUNT + 1)]


def test_exact_message_format(tower):
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T10:01:00")
    [message] = run_tower(tower)
    assert set(message) == {"type", "runway_id", "aircraft_id", "phase", "timestamp"}
    assert message["type"] == RUNWAY_STATUS
    assert (message["runway_id"], message["aircraft_id"], message["phase"]) == (1, "A1", "LANDING_ASSIGNED")
    assert command_inbox()[-1] == message  # what was returned is exactly what command got


def test_nothing_changed_sends_nothing(tower):
    assert send_runway_status(tower, "JFK") == []
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T10:01:00")
    run_tower(tower)
    assert run_tower(tower) == []


def test_only_the_changed_runway_is_sent(tower):
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T10:01:00")
    run_tower(tower)
    radar_sends("REQUEST_TAKEOFF", "B2", "2026-11-15T10:02:00")
    assert what_changed(run_tower(tower)) == [(2, "B2", "TAKEOFF_ASSIGNED")]


def test_every_phase_reaches_command(tower):
    steps = [
        ("REQUEST_LANDING", "2026-11-15T10:01:00", [(1, "A1", "LANDING_ASSIGNED")]),
        ("LANDED",          "2026-11-15T10:05:00", [(1, "A1", "LANDED")]),
        ("REQUEST_TAKEOFF", "2026-11-15T11:00:00", [(1, "A1", "TAKEOFF_ASSIGNED")]),
        ("DEPARTED",        "2026-11-15T11:05:00", [(1, None, None)]),
    ]
    for message_type, timestamp, expected in steps:
        radar_sends(message_type, "A1", timestamp)
        assert what_changed(run_tower(tower)) == expected, message_type


def test_parked_frees_the_runway_for_command(tower):
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T10:01:00")
    run_tower(tower)
    radar_sends("PARKED", "A1", "2026-11-15T10:10:00")
    assert what_changed(run_tower(tower)) == [(1, None, None)]


def test_same_state_again_later_is_sent_again(tower):
    # A1 lands on runway 1, departs, then lands on runway 1 again: command must hear the second landing too.
    for message_type, timestamp in [("REQUEST_LANDING", "2026-11-15T10:01:00"), ("DEPARTED", "2026-11-15T10:30:00")]:
        radar_sends(message_type, "A1", timestamp)
        run_tower(tower)
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T12:00:00")
    assert what_changed(run_tower(tower)) == [(1, "A1", "LANDING_ASSIGNED")]


def test_runway_status_comes_after_tower_acted(tower):
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T10:01:00")
    run_tower(tower)
    radar_sends("LANDED", "A1", "2026-11-15T10:05:00")
    assert send_runway_status(tower, "JFK") == []  # tower hasn't handled LANDED yet, so nothing changed
    run_tower(tower)
    last_two = command_inbox()[-2:]
    assert [m["type"] for m in last_two] == [AIRCRAFT_LANDED, RUNWAY_STATUS]
    assert last_two[1]["phase"] == "LANDED"


def test_no_runway_status_goes_to_radar(tower):
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T10:01:00")
    run_tower(tower)
    to_radar = [json.loads(m["content"]) for m in tower_db.get_messages("radar")]
    assert [m["type"] for m in to_radar] == ["RUNWAY_ASSIGNED"]


def fill_every_runway(conn):
    for n in range(1, RUNWAY_COUNT + 1):
        radar_sends("REQUEST_LANDING", f"P{n}", "2026-11-15T10:00:00")
    run_tower(conn)


def test_no_runway_is_also_sent_to_command(tower):
    fill_every_runway(tower)
    radar_sends("REQUEST_LANDING", "LATE", "2026-11-15T10:01:00")
    run_tower(tower)
    to_radar = [json.loads(m["content"]) for m in tower_db.get_messages("radar")]
    expected = {"type": NO_RUNWAY, "aircraft_id": "LATE", "request": "REQUEST_LANDING",
                "request_timestamp": "2026-11-15T10:01:00"}
    assert to_radar[-1] == expected
    assert command_inbox()[-1] == expected  # command gets exactly what radar got


def test_no_runway_reaches_command_once(tower):
    fill_every_runway(tower)
    radar_sends("REQUEST_LANDING", "LATE", "2026-11-15T10:01:00")
    run_tower(tower)
    run_tower(tower)
    assert [m["aircraft_id"] for m in command_inbox() if m["type"] == NO_RUNWAY] == ["LATE"]


def test_only_refusals_are_copied_to_command(tower):
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T10:01:00")
    run_tower(tower)
    assert {m["type"] for m in command_inbox()} == {RUNWAY_STATUS}  # RUNWAY_ASSIGNED stays radar's


def test_waiting_plane_later_shows_up_on_a_runway(tower):
    fill_every_runway(tower)
    radar_sends("REQUEST_LANDING", "LATE", "2026-11-15T10:01:00")
    run_tower(tower)
    radar_sends("DEPARTED", "P4", "2026-11-15T10:10:00")
    radar_sends("REQUEST_LANDING", "LATE", "2026-11-15T10:11:00")  # radar asks again
    assert what_changed(run_tower(tower)) == [(4, "LATE", "LANDING_ASSIGNED")]  # the wait is over


def test_command_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # tower.db gets created here, not in the repo
    monkeypatch.setattr("sys.argv", ["python -m src.tower.airport", "answer-requests"])
    cli.main()
    out = capsys.readouterr().out
    assert "Runway 1: told command it is free" in out and f"Runway {RUNWAY_COUNT}: told command it is free" in out
    cli.main()
    assert capsys.readouterr().out.strip() == "Nothing new to answer."
    radar_sends("REQUEST_LANDING", "A1", "2026-11-15T10:01:00")
    cli.main()
    assert "Runway 1: told command A1 is LANDING_ASSIGNED" in capsys.readouterr().out
    for n in range(2, RUNWAY_COUNT + 1):
        radar_sends("REQUEST_LANDING", f"P{n}", "2026-11-15T10:01:00")
    radar_sends("REQUEST_LANDING", "LATE", "2026-11-15T10:01:00")
    cli.main()
    assert "LATE: no runway available (told command)" in capsys.readouterr().out
