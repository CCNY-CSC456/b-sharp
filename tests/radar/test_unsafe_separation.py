# REQ-RAD-017
# Automated tests for radar answering tower's UNSAFE_SEPARATION messages. CI runs these with: pytest tests/radar
# Every test uses an in-memory database and fake messaging, so tower doesn't need to run.

import json
from datetime import datetime

from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.separation import handle_unsafe_separation

MEM = ":memory:"
OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)
NOW = datetime(2026, 11, 19, 14, 0, 0)


def plane(aircraft_id="B2", latitude=40.70, longitude=-73.80, altitude=3000):
    return AircraftTelemetry(aircraft_id=aircraft_id, latitude=latitude, longitude=longitude,
                             altitude=altitude, status="Landing", timestamp=OLD_TIME)


def from_tower(payload):
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return {"sender": "tower", "recipient": "radar", "content": content}


def unsafe(separation_id=7, aircraft_id="B2", latitude=40.81, longitude=-73.80, timestamp="2026-11-19T13:59:00"):
    """Exactly what tower sends (REQ-TOW-013)."""
    return from_tower({"type": "UNSAFE_SEPARATION", "separation_id": separation_id, "aircraft_id": aircraft_id,
                       "other_aircraft_id": "A1", "move_to_latitude": latitude, "move_to_longitude": longitude,
                       "timestamp": timestamp})


def setup(*planes):
    conn = init_db(MEM)
    for p in planes or (plane(),):
        create_aircraft(conn, p)
    return conn


def test_moves_the_plane_to_the_spot_tower_sent():
    conn = setup()
    handle_unsafe_separation(conn, [unsafe()], send=lambda raw: None, clock=lambda: NOW)
    moved = get_aircraft(conn, "B2")
    assert (moved.latitude, moved.longitude) == (40.81, -73.80)
    assert moved.altitude == 3000          # tower says the mover keeps its altitude
    assert moved.timestamp == NOW


def test_replies_resolved_then_sends_the_new_position():
    conn = setup()
    sent = []
    handle_unsafe_separation(conn, [unsafe()], send=sent.append, clock=lambda: NOW)
    resolved, info = (json.loads(raw) for raw in sent)
    assert resolved == {"type": "UNSAFE_SEPARATION_RESOLVED", "separation_id": 7, "aircraft_id": "B2",
                        "timestamp": "2026-11-19T14:00:00"}
    assert info["type"] == "AIRCRAFT_INFO"
    assert (info["latitude"], info["longitude"]) == (40.81, -73.80)


def test_returns_what_happened():
    conn = setup()
    results = handle_unsafe_separation(conn, [unsafe()], send=lambda raw: None, clock=lambda: NOW)
    assert results == ["B2: moved to (40.81, -73.8) for unsafe separation 7"]


def test_each_event_is_handled_once_even_though_the_inbox_keeps_it():
    # Radar's inbox returns every message ever sent, so the same UNSAFE_SEPARATION comes back every run.
    conn = setup()
    sent = []
    handle_unsafe_separation(conn, [unsafe()], send=sent.append, clock=lambda: NOW)
    # Afterwards the plane moves on its own (e.g. a later update)...
    conn.execute("UPDATE aircraft SET latitude = 41.5 WHERE aircraft_id = 'B2'")
    # ...and the old message must NOT drag it back.
    assert handle_unsafe_separation(conn, [unsafe()], send=sent.append, clock=lambda: NOW) == []
    assert len(sent) == 2
    assert get_aircraft(conn, "B2").latitude == 41.5


def test_a_new_event_with_a_reused_id_is_still_handled():
    # If tower.db is reset, separation_id starts at 1 again; the timestamp tells the events apart.
    conn = setup()
    first = unsafe(separation_id=1, latitude=40.81, timestamp="2026-11-19T10:00:00")
    second = unsafe(separation_id=1, latitude=40.59, timestamp="2026-11-19T13:00:00")
    handle_unsafe_separation(conn, [first], send=lambda raw: None, clock=lambda: NOW)
    handle_unsafe_separation(conn, [first, second], send=lambda raw: None, clock=lambda: NOW)
    assert get_aircraft(conn, "B2").latitude == 40.59


def test_several_planes_in_one_run():
    conn = setup(plane("B2"), plane("C3", latitude=40.9))
    inbox = [unsafe(7, "B2", 40.81, -73.80), unsafe(8, "C3", 41.01, -73.91)]
    sent = []
    results = handle_unsafe_separation(conn, inbox, send=sent.append, clock=lambda: NOW)
    assert len(results) == 2
    assert get_aircraft(conn, "C3").latitude == 41.01
    assert [json.loads(raw)["type"] for raw in sent].count("UNSAFE_SEPARATION_RESOLVED") == 2


def test_ignores_messages_radar_should_not_trust():
    conn = setup()
    sent = []
    good = json.loads(unsafe()["content"])
    inbox = [
        from_tower("not json at all"),
        from_tower({**good, "separation_id": True}),             # bool is not an id
        from_tower({**good, "separation_id": "7"}),
        from_tower({**good, "move_to_latitude": "north"}),
        from_tower({**good, "move_to_latitude": None}),           # tower's WAITING copy (command only)
        from_tower({**good, "move_to_latitude": float("nan")}),
        from_tower({**good, "move_to_latitude": 95.0}),           # off the globe
        from_tower({**good, "move_to_longitude": -181.0}),
        from_tower({**good, "aircraft_id": 42}),
        from_tower({**good, "type": "SOMETHING_ELSE"}),
        {"sender": "command", "recipient": "radar", "content": unsafe()["content"]},  # only tower moves planes
    ]
    assert handle_unsafe_separation(conn, inbox, send=sent.append, clock=lambda: NOW) == []
    assert sent == []
    assert get_aircraft(conn, "B2").latitude == 40.70


def test_unknown_plane_is_skipped():
    conn = setup()
    sent = []
    assert handle_unsafe_separation(conn, [unsafe(aircraft_id="ZZ9")], send=sent.append, clock=lambda: NOW) == []
    assert sent == []
