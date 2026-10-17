# REQ-RAD-013
# Automated tests for radar's runway requests to tower. CI runs these with: pytest tests/radar
# Every test uses an in-memory database and fake messaging, so tower doesn't need to run.

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db, update_runway
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.runway_requests import (
    check_tower_replies, fake_tower_reply, request_landing, request_takeoff,
)

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)


def setup_plane(aircraft_id="AA123"):
    conn = init_db(":memory:")
    create_aircraft(conn, AircraftTelemetry(
        aircraft_id=aircraft_id, latitude=40.7769, longitude=-73.8740,
        altitude=0, status="Parked", timestamp=OLD_TIME,
    ))
    return conn


def from_tower(reply):
    # One fake inbox message from tower to radar. Dicts are turned into JSON text.
    content = reply if isinstance(reply, str) else json.dumps(reply)
    return {"sender": "tower", "recipient": "radar", "content": content}


def assigned(runway_id, aircraft_id="AA123"):
    return from_tower({"type": "RUNWAY_ASSIGNED", "aircraft_id": aircraft_id, "runway_id": runway_id})


# --- radar -> tower ---

def test_request_landing_sends_json():
    conn = setup_plane()
    sent = []  # a fake "messaging service" that just remembers what it was given
    request_landing(conn, "AA123", send=sent.append)
    message = json.loads(sent[0])
    assert message["type"] == "REQUEST_LANDING"
    assert message["aircraft_id"] == "AA123"
    datetime.strptime(message["timestamp"], "%Y-%m-%dT%H:%M:%S")  # fails if the format is wrong


def test_request_takeoff_sends_json():
    conn = setup_plane()
    sent = []
    request_takeoff(conn, "AA123", send=sent.append)
    assert json.loads(sent[0])["type"] == "REQUEST_TAKEOFF"


def test_request_for_missing_plane_raises():
    conn = setup_plane()
    sent = []
    with pytest.raises(ValueError):
        request_landing(conn, "NOPE", send=sent.append)
    assert sent == []  # nothing was sent to tower


# --- tower -> radar ---

def test_runway_assigned_sets_runway_and_timestamp():
    conn = setup_plane()
    results = check_tower_replies(conn, get=lambda: [assigned("R1")])
    plane = get_aircraft(conn, "AA123")
    assert plane.runway_id == "R1"
    assert plane.timestamp > OLD_TIME
    assert results == ["AA123: runway R1 assigned"]


def test_no_runway_leaves_runway_unchanged():
    conn = setup_plane()
    update_runway(conn, "AA123", "R1")
    no_runway = from_tower({"type": "NO_RUNWAY", "aircraft_id": "AA123"})
    results = check_tower_replies(conn, get=lambda: [no_runway])
    assert get_aircraft(conn, "AA123").runway_id == "R1"
    assert results == ["AA123: no runway available"]


def test_checking_twice_is_harmless():
    conn = setup_plane()
    inbox = [assigned("R1")]
    check_tower_replies(conn, get=lambda: inbox)
    first = get_aircraft(conn, "AA123")
    results = check_tower_replies(conn, get=lambda: inbox)  # the same replies come back again
    assert get_aircraft(conn, "AA123") == first  # nothing changed, not even the timestamp
    assert results == ["AA123: already on runway R1"]


def test_newest_reply_wins():
    conn = setup_plane()
    check_tower_replies(conn, get=lambda: [assigned("R1"), assigned("R2")])
    assert get_aircraft(conn, "AA123").runway_id == "R2"


def test_bad_messages_are_skipped():
    conn = setup_plane()
    inbox = [
        from_tower("runway change approved"),                                   # not JSON
        from_tower({"type": "HELLO", "aircraft_id": "AA123"}),                  # unknown type
        assigned("R9", aircraft_id="ZZ999"),                                    # plane we don't have
        from_tower({"type": "RUNWAY_ASSIGNED", "aircraft_id": "AA123"}),        # no runway_id
        {"sender": "command", "recipient": "radar", "content": assigned("R7")["content"]},  # not from tower
    ]
    assert check_tower_replies(conn, get=lambda: inbox) == []
    assert get_aircraft(conn, "AA123").runway_id is None


# --- aircraft_repo.py ---

def test_get_aircraft_missing_returns_none():
    assert get_aircraft(init_db(":memory:"), "NOPE") is None


def test_update_runway_missing_plane_raises():
    with pytest.raises(ValueError):
        update_runway(init_db(":memory:"), "NOPE", "R1")


# --- fake tower reply (testing helper) ---

def test_fake_tower_reply_builds_the_right_json():
    sent = []
    fake_tower_reply("a1", "R1", send=sent.append)
    fake_tower_reply("a1", "", send=sent.append)  # empty runway = no runway
    assert json.loads(sent[0]) == {"type": "RUNWAY_ASSIGNED", "aircraft_id": "a1", "runway_id": "R1"}
    assert json.loads(sent[1]) == {"type": "NO_RUNWAY", "aircraft_id": "a1"}


def test_fake_tower_reply_is_read_by_check_tower_replies():
    conn = setup_plane()
    sent = []
    fake_tower_reply("AA123", "R1", send=sent.append)
    inbox = [from_tower(content) for content in sent]  # what radar's inbox would hold
    assert check_tower_replies(conn, get=lambda: inbox) == ["AA123: runway R1 assigned"]
    assert get_aircraft(conn, "AA123").runway_id == "R1"
