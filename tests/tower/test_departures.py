# REQ-TOW-011
# Automated tests for takeoff clearance and departures. CI runs these with: pytest tests/tower
# These use the real messaging service on a throwaway messages.db, in the same order radar sends:
#   created -> REQUEST_LANDING -> LANDED -> REQUEST_TAKEOFF -> DEPARTED

import json
import sqlite3

import pytest

from src.tower.airport import __main__ as cli
from src.tower.airport.airport_repo import create_airport, create_tables
from src.tower.airport.runway_requests import (
    DEPARTED, FREED, LANDED, NO_RUNWAY, REQUEST_LANDING, REQUEST_TAKEOFF, RUNWAY_ASSIGNED, answer_requests,
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


def runway(conn, runway_id):
    """The (status, aircraft_id) of one JFK runway."""
    return conn.execute(
        "SELECT status, aircraft_id FROM runways WHERE airport_id = 'JFK' AND runway_id = ?", (runway_id,)
    ).fetchone()


def radar_inbox():
    """Every reply tower has sent radar, as dicts."""
    return [json.loads(m["content"]) for m in tower_db.get_messages("radar")]


def test_land_then_take_off_then_depart():
    conn = new_airport()
    # The airplane data radar sends on create is not a request and is ignored.
    tower_db.save_message("radar", "tower", json.dumps({"aircraft_id": "A1", "status": "Landing"}))

    radar_sends(REQUEST_LANDING, "A1", "2026-10-21T22:59:57")
    assert answer_requests(conn, "JFK") == [{
        "type": RUNWAY_ASSIGNED, "aircraft_id": "A1", "runway_id": 1,
        "request": REQUEST_LANDING, "request_timestamp": "2026-10-21T22:59:57",
    }]

    radar_sends(LANDED, "A1", "2026-10-21T23:16:54")
    assert answer_requests(conn, "JFK") == []        # landed: still on its runway, nothing to say
    assert runway(conn, 1) == ("Not Available", "A1")

    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T23:18:46")
    clearance = answer_requests(conn, "JFK")
    assert clearance == [{
        "type": RUNWAY_ASSIGNED, "aircraft_id": "A1", "runway_id": 1,  # same runway it landed on
        "request": REQUEST_TAKEOFF, "request_timestamp": "2026-10-21T23:18:46",
    }]
    assert radar_inbox()[-1] == clearance[0]           # radar got its clearance for takeoff

    radar_sends(DEPARTED, "A1", "2026-10-21T23:32:10")
    assert answer_requests(conn, "JFK") == [{"type": FREED, "aircraft_id": "A1", "runway_id": 1}]
    assert runway(conn, 1) == ("Available", None)
    assert len(radar_inbox()) == 2                     # DEPARTED gets no reply

    assert answer_requests(conn, "JFK") == []          # running again changes nothing
    assert runway(conn, 1) == ("Available", None)      # the old requests don't take it back


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


def test_repeated_request_is_answered_once():
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
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-10-21T10:10:00")
    cli.main()
    assert "A1: cleared for takeoff on runway 1" in capsys.readouterr().out
    radar_sends(DEPARTED, "A1", "2026-10-21T10:20:00")
    cli.main()
    assert "A1: departed, runway 1 freed" in capsys.readouterr().out
    cli.main()
    assert "Nothing new to answer." in capsys.readouterr().out
