# REQ-RAD-017 / REQ-RAD-018
# Automated tests for radar's unsafe separation handling and continuous conflict signals.
# CI runs these with: pytest tests/radar

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db, update_position
from src.radar.airplane.conflict_signals import (
    check_unsafe_separation, fake_conflict_resolved, send_conflict_until_resolved,
)
from src.radar.airplane.models import AircraftTelemetry

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)
MEM = ":memory:"


def sample_plane(aircraft_id="AA123"):
    return AircraftTelemetry(
        aircraft_id=aircraft_id,
        latitude=40.7769,
        longitude=-73.8740,
        altitude=2000,
        status="Landing",
        timestamp=OLD_TIME,
    )


def from_tower(payload):
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return {"sender": "tower", "recipient": "radar", "content": content}


def from_radar(payload):
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return {"sender": "radar", "recipient": "tower", "content": content}


def unsafe_msg(separation_id=1, aircraft_id="AA123", lat=41.0, lon=-74.0):
    return from_tower({
        "type": "UNSAFE_SEPARATION",
        "separation_id": separation_id,
        "aircraft_id": aircraft_id,
        "move_to_latitude": lat,
        "move_to_longitude": lon,
    })


# --- unsafe separation ---

def test_unsafe_separation_moves_plane_and_replies():
    conn = init_db(MEM)
    create_aircraft(conn, sample_plane())
    sent = []

    results = check_unsafe_separation(conn, get=lambda: [unsafe_msg(1, "AA123", 41.25, -74.5)], send=sent.append)

    plane = get_aircraft(conn, "AA123")
    assert plane.latitude == 41.25
    assert plane.longitude == -74.5
    assert plane.timestamp > OLD_TIME
    assert results == ["AA123: moved to (41.25, -74.5) for separation 1"]

    resolved = json.loads(sent[0])
    assert resolved["type"] == "UNSAFE_SEPARATION_RESOLVED"
    assert resolved["separation_id"] == 1
    assert resolved["aircraft_id"] == "AA123"
    datetime.strptime(resolved["timestamp"], "%Y-%m-%dT%H:%M:%S")

    info = json.loads(sent[1])
    assert info["type"] == "AIRCRAFT_INFO"
    assert info["latitude"] == 41.25
    assert info["longitude"] == -74.5


def test_unsafe_separation_skips_already_resolved():
    conn = init_db(MEM)
    create_aircraft(conn, sample_plane())
    sent = []
    inbox = [
        unsafe_msg(1, "AA123", 41.25, -74.5),
        from_radar({"type": "UNSAFE_SEPARATION_RESOLVED", "separation_id": 1, "aircraft_id": "AA123"}),
    ]

    results = check_unsafe_separation(conn, get=lambda: inbox, send=sent.append)

    assert results == []
    assert sent == []
    assert get_aircraft(conn, "AA123").latitude == 40.7769


def test_unsafe_separation_ignores_bad_messages():
    conn = init_db(MEM)
    create_aircraft(conn, sample_plane())
    sent = []
    inbox = [
        from_tower("not json at all"),
        from_tower({"type": "UNSAFE_SEPARATION", "separation_id": True, "aircraft_id": "AA123", "move_to_latitude": 41.0, "move_to_longitude": -74.0}),
        from_tower({"type": "UNSAFE_SEPARATION", "separation_id": 2, "aircraft_id": "AA123", "move_to_latitude": "bad", "move_to_longitude": -74.0}),
        unsafe_msg(3, "UNKNOWN", 41.0, -74.0),
        {"sender": "command", "recipient": "radar", "content": unsafe_msg(4)["content"]},
    ]

    assert check_unsafe_separation(conn, get=lambda: inbox, send=sent.append) == []
    assert sent == []


# --- conflict signals ---

def test_send_conflict_stops_when_resolved():
    conn = init_db(MEM)
    create_aircraft(conn, sample_plane())
    sent = []
    inbox = []

    def fake_send(raw):
        sent.append(raw)
        # Simulate tower resolving the conflict after radar's 2nd CONFLICT message
        if len(sent) == 2:
            inbox.append(from_tower({"type": "CONFLICT_RESOLVED", "aircraft_id": "AA123"}))

    resolved = send_conflict_until_resolved(
        conn,
        "AA123",
        "Low on Gas",
        send=fake_send,
        get=lambda: inbox,
        interval_seconds=0,
        max_attempts=5,
    )

    assert resolved is True
    assert len(sent) == 3  # 2 CONFLICT messages + 1 final AIRCRAFT_INFO
    first_msg = json.loads(sent[0])
    assert first_msg["type"] == "CONFLICT"
    assert first_msg["aircraft_id"] == "AA123"
    assert first_msg["reason"] == "Low on Gas"
    assert json.loads(sent[2])["type"] == "AIRCRAFT_INFO"
    assert get_aircraft(conn, "AA123").timestamp > OLD_TIME


def test_send_conflict_times_out_at_max_attempts():
    conn = init_db(MEM)
    create_aircraft(conn, sample_plane())
    sent = []

    resolved = send_conflict_until_resolved(
        conn,
        "AA123",
        "Late by +2 hour",
        send=sent.append,
        get=lambda: [],
        interval_seconds=0,
        max_attempts=3,
    )

    assert resolved is False
    assert len(sent) == 3
    assert all(json.loads(m)["type"] == "CONFLICT" for m in sent)


def test_send_conflict_validates_plane_and_reason():
    conn = init_db(MEM)
    create_aircraft(conn, sample_plane())

    with pytest.raises(ValueError):
        send_conflict_until_resolved(conn, "NOPE", "Low on Gas", interval_seconds=0)

    with pytest.raises(ValueError):
        send_conflict_until_resolved(conn, "AA123", "Engine Fire", interval_seconds=0)


# --- aircraft_repo & testing helper ---

def test_update_position_missing_plane_raises():
    with pytest.raises(ValueError):
        update_position(init_db(MEM), "NOPE", 41.0, -74.0)


def test_fake_conflict_resolved_helper():
    sent = []
    fake_conflict_resolved("AA123", send=sent.append)
    parsed = json.loads(sent[0])
    assert parsed["type"] == "CONFLICT_RESOLVED"
    assert parsed["aircraft_id"] == "AA123"