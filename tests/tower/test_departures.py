# REQ-TOW-011
# Automated tests for takeoff clearance and departures. CI runs these with: pytest tests/tower
# These use the real messaging service on a throwaway messages.db, in the same order radar sends:
#   created -> REQUEST_LANDING -> LANDED -> REQUEST_TAKEOFF -> DEPARTED
#   created -> REQUEST_LANDING -> LANDED -> PARKED (frees the runway)

import json
import sqlite3

import pytest

from src.tower.airport import __main__ as cli
from src.tower.airport.airport_repo import VALID_TRANSITIONS, create_airport, create_tables
from src.tower.airport.runway_requests import (
    DEPARTED, FREED, LANDED, NO_RUNWAY, PARKED, REQUEST_LANDING, REQUEST_REFUSED, REQUEST_TAKEOFF, RUNWAY_ASSIGNED,
    answer_requests,
)
from src.tower.messaging import db as tower_db


@pytest.fixture(autouse=True)
def throwaway_messages(tmp_path, monkeypatch):
    # Point the shared messages.db at a throwaway file so we never touch the real one.
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "messages.db"))
    tower_db.init_db()


def new_airport():
    conn = sqlite3.connect(":memory:")  # a throwaway database that only lives in RAM
    create_tables(conn)
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    return conn


def radar_sends(message_type, aircraft_id, timestamp):
    """Put a message in tower's inbox exactly like radar does."""
    content = {"type": message_type, "aircraft_id": aircraft_id, "timestamp": timestamp}
    tower_db.save_message("radar", "tower", json.dumps(content))

################################################################################
def runway(conn, runway_id):
    """Return ("Not Available", aircraft_id) if assigned, else ("Available", None)."""
    row = conn.execute(
        "SELECT aircraft_id FROM runway_assignments WHERE airport_id = 'JFK' AND runway_id = ?",
        (runway_id,)
    ).fetchone()

    if row is None:
        return ("Available", None)
    return ("Not Available", row[0])
################################################################################

def radar_inbox():
    """Every reply tower has sent radar, as dicts."""
    return [json.loads(m["content"]) for m in tower_db.get_messages("radar")]

################################################################################

def test_land_then_take_off_then_depart(): # TODO stil fails
    conn = new_airport()

    # 1. Ignored non-request payload
    tower_db.save_message("radar", "tower", json.dumps({"aircraft_id": "A1", "status": "Landing"}))

    # 2. Request landing
    radar_sends(REQUEST_LANDING, "A1", "2026-10-21T22:59:57")
    assert answer_requests(conn, "JFK") == [{
        "type": RUNWAY_ASSIGNED, "aircraft_id": "A1", "runway_id": 1,
        "request": REQUEST_LANDING, "request_timestamp": "2026-10-21T22:59:57",
    }]

    # 3. Landed (holds runway, emits no external reply)
    radar_sends(LANDED, "A1", "2026-10-21T23:16:54")
    assert answer_requests(conn, "JFK") == []
    assert runway(conn, 1) == ("Not Available", "A1")

    # 4. Request takeoff (gets same runway)
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T23:18:46")
    assert answer_requests(conn, "JFK") == [{
        "type": RUNWAY_ASSIGNED, "aircraft_id": "A1", "runway_id": 1,
        "request": REQUEST_TAKEOFF, "request_timestamp": "2026-10-21T23:18:46",
    }]

    # 5. Departed (frees runway, emits FREED internally)
    radar_sends(DEPARTED, "A1", "2026-10-21T23:32:10")
    assert answer_requests(conn, "JFK") == [{"type": FREED, "aircraft_id": "A1", "runway_id": 1}]
    assert runway(conn, 1) == ("Available", None)

    # 6. Idempotency (re-running does nothing)
    assert answer_requests(conn, "JFK") == []
    assert runway(conn, 1) == ("Available", None)

################################################################################

def test_landed_keeps_the_runway_for_that_plane():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-10-21T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(LANDED, "A1", "2026-10-21T10:05:00")
    radar_sends(REQUEST_LANDING, "B2", "2026-10-21T10:06:00")
    answer_requests(conn, "JFK")
    assert runway(conn, 1) == ("Not Available", "A1")
    assert runway(conn, 2) == ("Not Available", "B2")  # B2 never gets A1's runway


def test_freed_runway_goes_to_the_next_plane():
    conn = new_airport()
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(DEPARTED, "A1", "2026-10-21T10:05:00")
    radar_sends(REQUEST_LANDING, "B2", "2026-10-21T10:06:00")
    results = answer_requests(conn, "JFK")
    assert {"type": FREED, "aircraft_id": "A1", "runway_id": 1} in results
    assert runway(conn, 1) == ("Not Available", "B2")  # A1 freed it first, so B2 gets it


def test_same_id_after_departing_is_answered_again():
    # Radar deletes a departed plane, so the same ID can be created and used again.
    conn = new_airport()
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(DEPARTED, "A1", "2026-10-21T10:05:00")
    answer_requests(conn, "JFK")
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T11:00:00")  # a new A1, same runway as before
    replies = answer_requests(conn, "JFK")
    assert replies[0]["runway_id"] == 1
    assert replies[0]["request_timestamp"] == "2026-10-21T11:00:00"  # a new reply, not skipped


def test_repeated_request_is_answered_once(): # TODO fails from message gc
    conn = new_airport()
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T10:00:00")
    answer_requests(conn, "JFK")
    assert answer_requests(conn, "JFK") == []
    assert len(radar_inbox()) == 1


def test_departed_without_a_runway_does_nothing():
    conn = new_airport()
    radar_sends(DEPARTED, "A1", "2026-10-21T10:00:00")
    assert answer_requests(conn, "JFK") == []
    assert radar_inbox() == []


def test_no_runway_reply_says_which_request():
    conn = new_airport()
    for n in range(1, 12):  # 11 planes, 10 runways
        radar_sends(REQUEST_LANDING, f"PLANE{n}", f"2026-10-21T10:00:{n:02d}")
    replies = answer_requests(conn, "JFK")
    assert replies[-1] == {
        "type": NO_RUNWAY, "aircraft_id": "PLANE11",
        "request": REQUEST_LANDING, "request_timestamp": "2026-10-21T10:00:11",
    }


def test_radar_reads_the_takeoff_clearance():
    from src.radar.airplane.runway_requests import read_reply  # radar's own reader
    conn = new_airport()
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T10:00:00")
    answer_requests(conn, "JFK")
    message = tower_db.get_messages("radar")[-1]
    assert read_reply(message)["request"] == REQUEST_TAKEOFF


def test_command_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # tower.db gets created here, not in the repo
    monkeypatch.setattr("sys.argv", ["python -m src.tower.airport", "answer-requests"])
    radar_sends(REQUEST_LANDING, "A1", "2026-10-21T10:00:00")
    cli.main()
    assert "A1: cleared to land on runway 1" in capsys.readouterr().out
    radar_sends(LANDED, "A1", "2026-10-21T10:05:00")
    cli.main()
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T10:10:00")
    cli.main()
    assert "A1: cleared for takeoff on runway 1" in capsys.readouterr().out
    radar_sends(DEPARTED, "A1", "2026-10-21T10:20:00")
    cli.main()
    assert "A1: departed, runway 1 freed" in capsys.readouterr().out
    cli.main()
    assert "Nothing new to answer." in capsys.readouterr().out


# --- PARKED frees the runway ---

def test_parked_frees_the_runway():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-15T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(LANDED, "A1", "2026-11-15T10:05:00")
    answer_requests(conn, "JFK")
    assert runway(conn, 1) == ("Not Available", "A1")  # landed: still on its runway
    radar_sends(PARKED, "A1", "2026-11-15T10:10:00")
    assert answer_requests(conn, "JFK") == [
        {"type": FREED, "aircraft_id": "A1", "runway_id": 1, "reason": PARKED},
    ]
    assert runway(conn, 1) == ("Available", None)
    assert len(radar_inbox()) == 1  # only the landing clearance: PARKED gets no reply


def test_parked_runway_goes_to_the_next_plane():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-15T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(PARKED, "A1", "2026-11-15T10:10:00")
    radar_sends(REQUEST_LANDING, "B2", "2026-11-15T10:11:00")
    answer_requests(conn, "JFK")
    assert runway(conn, 1) == ("Not Available", "B2")


def test_old_request_is_not_answered_again_after_parking():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-15T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(PARKED, "A1", "2026-11-15T10:10:00")
    answer_requests(conn, "JFK")
    assert answer_requests(conn, "JFK") == []
    assert runway(conn, 1) == ("Available", None)  # the old landing request doesn't take it back


def test_parked_plane_can_ask_to_take_off():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-15T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(PARKED, "A1", "2026-11-15T10:10:00")
    answer_requests(conn, "JFK")
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-15T11:00:00")
    results = answer_requests(conn, "JFK")
    assert results[0]["type"] == RUNWAY_ASSIGNED and results[0]["request"] == REQUEST_TAKEOFF


def test_parked_without_a_runway_does_nothing():
    conn = new_airport()
    radar_sends(PARKED, "A1", "2026-11-15T10:00:00")
    assert answer_requests(conn, "JFK") == []


def test_parked_command_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # tower.db gets created here, not in the repo
    monkeypatch.setattr("sys.argv", ["python -m src.tower.airport", "answer-requests"])
    radar_sends(REQUEST_LANDING, "A1", "2026-11-15T10:00:00")
    cli.main()
    capsys.readouterr()
    radar_sends(PARKED, "A1", "2026-11-15T10:10:00")
    cli.main()
    assert "A1: parked, runway 1 freed" in capsys.readouterr().out


# --- the runway's phase: LANDING_ASSIGNED -> LANDED -> TAKEOFF_ASSIGNED ---

def phase(conn, aircraft_id):
    row = conn.execute(
        "SELECT status FROM runway_assignments WHERE airport_id = 'JFK' AND aircraft_id = ?", (aircraft_id,)
    ).fetchone()
    return None if row is None else row[0]


def test_runway_phase_follows_the_plane():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-15T10:00:00")
    answer_requests(conn, "JFK")
    assert phase(conn, "A1") == "LANDING_ASSIGNED"
    radar_sends(LANDED, "A1", "2026-11-15T10:05:00")
    assert answer_requests(conn, "JFK") == []  # no reply to radar
    assert phase(conn, "A1") == "LANDED"
    assert runway(conn, 1) == ("Not Available", "A1")  # landed: still holds the runway
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-15T10:20:00")
    answer_requests(conn, "JFK")
    assert phase(conn, "A1") == "TAKEOFF_ASSIGNED"


def test_takeoff_from_the_ground_is_takeoff_assigned():
    conn = new_airport()
    radar_sends(REQUEST_TAKEOFF, "B2", "2026-11-15T10:00:00")
    answer_requests(conn, "JFK")
    assert phase(conn, "B2") == "TAKEOFF_ASSIGNED"


def test_landed_without_a_runway_does_nothing():
    conn = new_airport()
    radar_sends(LANDED, "A1", "2026-11-15T10:05:00")
    assert answer_requests(conn, "JFK") == []
    assert phase(conn, "A1") is None


# --- requests that don't fit the plane's phase are refused, and never stop tower ---

def test_every_allowed_phase_is_a_real_phase():
    # runway_assignments only allows these (PARKED / DEPARTED free the runway instead).
    real = {None, "LANDING_ASSIGNED", "LANDED", "TAKEOFF_ASSIGNED"}
    assert all(old in real and new in real for old, new in VALID_TRANSITIONS)


def test_takeoff_before_landing_is_refused_and_tower_keeps_going():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-17T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-17T10:05:00")  # A1 hasn't reported LANDED
    radar_sends(REQUEST_LANDING, "B2", "2026-11-17T10:05:00")
    answer_requests(conn, "JFK")  # used to raise ValueError and stop every run after it
    replies = {(r["aircraft_id"], r["type"]): r for r in radar_inbox()}
    assert replies[("A1", REQUEST_REFUSED)] == {
        "type": REQUEST_REFUSED, "aircraft_id": "A1", "phase": "LANDING_ASSIGNED",
        "reason": "A1 is LANDING_ASSIGNED, so it can't get TAKEOFF_ASSIGNED",
        "request": REQUEST_TAKEOFF, "request_timestamp": "2026-11-17T10:05:00"}
    assert replies[("B2", RUNWAY_ASSIGNED)]["runway_id"] == 2  # the other plane is still answered
    assert phase(conn, "A1") == "LANDING_ASSIGNED"             # nothing changed for A1
    assert answer_requests(conn, "JFK") == []                  # handled once, not again every run


def test_refused_is_only_told_to_radar():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-17T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-17T10:05:00")
    answer_requests(conn, "JFK")
    to_command = [json.loads(m["content"]) for m in tower_db.get_messages("command")]
    assert not any(m["type"] in (REQUEST_REFUSED, NO_RUNWAY) for m in to_command)  # no false "waiting" alert


def test_landing_again_after_landed_is_refused():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-17T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(LANDED, "A1", "2026-11-17T10:05:00")
    answer_requests(conn, "JFK")
    radar_sends(REQUEST_LANDING, "A1", "2026-11-17T10:06:00")
    [reply] = answer_requests(conn, "JFK")
    assert reply["type"] == REQUEST_REFUSED and reply["phase"] == "LANDED"
    assert phase(conn, "A1") == "LANDED"


def test_refused_plane_can_carry_on_normally():
    conn = new_airport()
    radar_sends(REQUEST_LANDING, "A1", "2026-11-17T10:00:00")
    answer_requests(conn, "JFK")
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-17T10:05:00")
    answer_requests(conn, "JFK")  # refused
    radar_sends(LANDED, "A1", "2026-11-17T10:06:00")
    answer_requests(conn, "JFK")
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-17T10:10:00")
    [reply] = answer_requests(conn, "JFK")
    assert (reply["type"], reply["runway_id"]) == (RUNWAY_ASSIGNED, 1)
    assert phase(conn, "A1") == "TAKEOFF_ASSIGNED"


def test_refused_command_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["python -m src.tower.airport", "answer-requests"])
    radar_sends(REQUEST_LANDING, "A1", "2026-11-17T10:00:00")
    cli.main()
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-17T10:05:00")
    cli.main()
    assert "A1: REQUEST_TAKEOFF refused, it is LANDING_ASSIGNED (told radar)" in capsys.readouterr().out
