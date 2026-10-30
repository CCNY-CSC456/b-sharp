# REQ-TOW-008
# Automated tests for answering radar's runway requests. CI runs these with: pytest tests/tower

import json
import sqlite3

from src.tower.airport import __main__ as cli
from src.tower.airport.airport_repo import create_airport, create_tables
from src.tower.airport.runway_requests import (
    NO_RUNWAY, REQUEST_LANDING, REQUEST_TAKEOFF, RUNWAY_ASSIGNED, answer_requests, read_request,
)
from src.tower.messaging import db as tower_db


def new_airport():
    conn = sqlite3.connect(":memory:")  # a throwaway database that only lives in RAM
    create_tables(conn)
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    return conn


def radar_request(aircraft_id, request_type=REQUEST_LANDING):
    """An inbox message exactly like the ones radar sends."""
    content = {"type": request_type, "aircraft_id": aircraft_id, "timestamp": "2026-10-18T14:30:00"}
    return {"sender": "radar", "recipient": "tower", "content": json.dumps(content)}


def answer(conn, inbox, already_sent=()):
    """Run answer_requests with fake inboxes. Returns (replies it returned, replies it sent)."""
    sent = []  # a fake "messaging service" that just remembers what it was given
    replies = answer_requests(
        conn, "JFK",
        get=lambda: inbox,
        send=lambda content: sent.append(json.loads(content)),
    )
    return replies, sent


# --- reading requests ---

def test_reads_landing_and_takeoff_requests():
    assert read_request(radar_request("AA123", REQUEST_LANDING))["aircraft_id"] == "AA123"
    assert read_request(radar_request("AA123", REQUEST_TAKEOFF))["type"] == REQUEST_TAKEOFF


def test_ignores_messages_that_are_not_runway_requests():
    assert read_request({"sender": "command", "recipient": "tower", "content": radar_request("AA123")["content"]}) is None
    assert read_request({"sender": "radar",   "recipient": "tower", "content": "hello tower"}) is None
    assert read_request({"sender": "radar",   "recipient": "tower", "content": '{"aircraft_id": "AA123", "status": "Parked"}'}) is None
    assert read_request({"sender": "radar",   "recipient": "tower", "content": '{"type": "REQUEST_LANDING"}'}) is None


# --- answering requests ---

def test_assigns_a_runway_and_replies():
    replies, sent = answer(new_airport(), [radar_request("AA123")])
    assert sent == [{
        "type": RUNWAY_ASSIGNED, "aircraft_id": "AA123", "runway_id": 1,
        "request": REQUEST_LANDING, "request_timestamp": "2026-10-18T14:30:00",  # REQ-TOW-011
    }]
    assert replies == sent


def test_two_airplanes_get_different_runways():
    _, sent = answer(new_airport(), [radar_request("AA123"), radar_request("UA456", REQUEST_TAKEOFF)])
    assert [reply["runway_id"] for reply in sent] == [1, 2]


def test_no_runway_when_all_are_taken():
    inbox = [radar_request(f"PLANE{n}") for n in range(1, 12)]  # 11 planes, 10 runways
    _, sent = answer(new_airport(), inbox)
    assert sent[-1]["type"] == NO_RUNWAY
    assert sent[-1]["aircraft_id"] == "PLANE11"


def test_same_request_twice_gets_one_reply():
    _, sent = answer(new_airport(), [radar_request("AA123"), radar_request("AA123")])
    assert len(sent) == 1


def test_running_again_sends_nothing_new():
    # The inbox keeps every message, so the second run sees the same request again.
    conn = new_airport()
    inbox = [radar_request("AA123")]
    _, first = answer(conn, inbox)
    already_sent = [{"sender": "tower", "recipient": "radar", "content": json.dumps(reply)} for reply in first]
    _, second = answer(conn, inbox, already_sent)
    assert second == []


# --- radar accepts tower's replies ---

def test_radar_can_read_towers_replies():
    from src.radar.airplane.runway_requests import read_reply  # radar's own reader
    inbox = [radar_request(f"PLANE{n}") for n in range(1, 12)]
    _, sent = answer(new_airport(), inbox)
    for reply in (sent[0], sent[-1]):  # one RUNWAY_ASSIGNED and one NO_RUNWAY
        message = {"sender": "tower", "recipient": "radar", "content": json.dumps(reply)}
        assert read_reply(message) == reply


def test_full_round_trip_with_radar(tmp_path, monkeypatch):
    # Point the shared messages.db at a throwaway file so we never touch the real one.
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "messages.db"))
    from src.radar.airplane.aircraft_repo import get_aircraft, init_db as init_radar_db
    from src.radar.airplane.create_airplane import create_airplane
    from src.radar.airplane.runway_requests import check_tower_replies, request_landing

    radar = init_radar_db(":memory:")
    create_airplane(radar, "AA123", 40.77, -73.87, 2000, "Landing", send=lambda plane: None)
    request_landing(radar, "AA123")      # radar -> tower
    answer_requests(new_airport(), "JFK")  # tower reads it and replies (real messaging)
    check_tower_replies(radar)           # radar reads the reply
    assert get_aircraft(radar, "AA123").runway_id == "1"


# --- answer-requests command (__main__.py) ---

def test_answer_requests_command(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # tower.db and messages.db get created here, not in the repo
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "messages.db"))
    tower_db.init_db()
    tower_db.save_message("radar", "tower", radar_request("AA123")["content"])
    monkeypatch.setattr("sys.argv", ["python -m src.tower.airport", "answer-requests"])
    cli.main()
    assert "AA123: cleared to land on runway 1" in capsys.readouterr().out
    cli.main()  # second run: nothing new to say
    assert "Nothing new to answer." in capsys.readouterr().out
