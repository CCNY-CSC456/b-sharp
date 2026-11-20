# REQ-RAD-017, REQ-RAD-018, REQ-RAD-019
# Automated tests for radar's run loop: everything R2 needs, once per second, for every plane at once.
# CI runs these with: pytest tests/radar

import json
import time
from datetime import datetime, timedelta


from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db
from src.radar.airplane.conflicts import get_conflicts, open_conflict
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.monitor import run, tick
from src.tower.messaging import db as tower_db

MEM = ":memory:"
OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)
T0 = datetime(2026, 11, 19, 14, 0, 0)


def BAD_PLANE_MACRO(aircraft_id, status="Landing", latitude=40.7):
    return AircraftTelemetry(aircraft_id=aircraft_id, latitude=latitude, longitude=-73.8, altitude=3000,
                             status=status, timestamp=OLD_TIME)


def from_tower(payload):
    return {"sender": "tower", "recipient": "radar", "content": json.dumps(payload)}


class Clock:
    def __init__(self):
        self.time = T0

    def __call__(self):
        return self.time

    def sleep(self, seconds):
        self.time += timedelta(seconds=seconds)


def resolved(aircraft_id, reason, conflict_id=1):
    return from_tower({"type": "CONFLICT_RESOLVED", "conflict_id": conflict_id, "aircraft_id": aircraft_id,
                       "reason": reason, "queue_position": 1, "timestamp": "2026-11-19T14:00:05"})


def test_one_tick_does_every_job():
    conn = init_db(MEM)
    create_aircraft(conn, BAD_PLANE_MACRO("B2"))
    create_aircraft(conn, BAD_PLANE_MACRO("C3"))
    open_conflict(conn, "C3", "LOW_FUEL", clock=lambda: T0)
    inbox = [
        from_tower({"type": "UNSAFE_SEPARATION", "separation_id": 1, "aircraft_id": "B2", "other_aircraft_id": "A1",
                    "move_to_latitude": 40.81, "move_to_longitude": -73.8, "timestamp": "2026-11-19T13:59:00"}),
        from_tower({"type": "RUNWAY_ASSIGNED", "aircraft_id": "B2", "runway_id": "R1",
                    "request": "REQUEST_LANDING", "request_timestamp": "2026-11-19T13:58:00"}),
    ]
    sent = []
    results = tick(conn, get=lambda: inbox, send=sent.append, clock=lambda: T0)
    assert get_aircraft(conn, "B2").latitude == 40.81
    assert get_aircraft(conn, "B2").runway_id == "R1"
    assert "CONFLICT" in [json.loads(raw)["type"] for raw in sent]
    assert len(results) >= 3

    inbox.append(resolved("C3", "Low on Gas"))
    sent.clear()
    tick(conn, get=lambda: inbox, send=sent.append, clock=lambda: T0 + timedelta(seconds=1))
    assert "CONFLICT" not in [json.loads(raw)["type"] for raw in sent]
    assert get_conflicts(conn)[0]["status"] == "RESOLVED"


def test_getting_a_runway_does_not_stop_the_signal_tower_does():
    # Tower decides when a conflict is over (REQ-TOW-015); radar keeps sending until CONFLICT_RESOLVED.
    conn = init_db(MEM)
    create_aircraft(conn, BAD_PLANE_MACRO("AA123"))
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: T0)
    inbox = [from_tower({"type": "RUNWAY_ASSIGNED", "aircraft_id": "AA123", "runway_id": "R1",
                         "request": "REQUEST_LANDING", "request_timestamp": "2026-11-19T13:59:00"})]
    sent = []
    tick(conn, get=lambda: inbox, send=sent.append, clock=lambda: T0)
    assert "CONFLICT" in [json.loads(raw)["type"] for raw in sent]
    assert get_conflicts(conn)[0]["status"] == "OPEN"


def test_tick_reads_the_inbox_once():
    conn = init_db(MEM)
    calls = []
    tick(conn, get=lambda: calls.append(1) or [], send=lambda raw: None, clock=lambda: T0)
    assert calls == [1]


def test_run_sends_conflict_every_second_until_tower_resolves():
    conn = init_db(MEM)
    create_aircraft(conn, BAD_PLANE_MACRO("AA123"))
    open_conflict(conn, "AA123", "LATE_2H", clock=lambda: T0)
    inbox, sent, clock = [], [], Clock()

    def send(raw):
        sent.append(raw)
        if sum(json.loads(r)["type"] == "CONFLICT" for r in sent) == 3:  # tower answers after the 3rd signal
            inbox.append(resolved("AA123", "Late by +2 hour"))

    run(conn, get=lambda: inbox, send=send, clock=clock, sleep=clock.sleep, ticks=10, out=lambda line: None)
    conflicts = [json.loads(raw) for raw in sent if json.loads(raw)["type"] == "CONFLICT"]
    assert len(conflicts) == 3
    assert [c["timestamp"] for c in conflicts] == ["2026-11-19T14:00:00", "2026-11-19T14:00:01", "2026-11-19T14:00:02"]
    assert clock.time == T0 + timedelta(seconds=10)   # one tick per second


def test_run_lands_a_plane_30_seconds_after_its_runway():
    conn = init_db(MEM)
    create_aircraft(conn, BAD_PLANE_MACRO("AA123"))
    inbox = [from_tower({"type": "RUNWAY_ASSIGNED", "aircraft_id": "AA123", "runway_id": "R1",
                         "request": "REQUEST_LANDING", "request_timestamp": "2026-11-19T13:59:59"})]
    sent, clock = [], Clock()
    run(conn, get=lambda: inbox, send=sent.append, clock=clock, sleep=clock.sleep, ticks=29, out=lambda line: None)
    assert sent == []
    run(conn, get=lambda: inbox, send=sent.append, clock=clock, sleep=clock.sleep, ticks=2, out=lambda line: None)
    assert [json.loads(raw)["type"] for raw in sent] == ["LANDED", "PARKED", "AIRCRAFT_INFO"]


def test_many_planes_in_one_tick_without_slowing_down():
    # AC: handles concurrent aircraft without degradation. 300 planes, each late, a 3000-message inbox,
    # all handled in ONE tick, well inside the 1 second between ticks.
    conn = init_db(MEM)
    ids = [f"P{n:03}" for n in range(300)]
    for n, aircraft_id in enumerate(ids):
        create_aircraft(conn, BAD_PLANE_MACRO(aircraft_id, latitude=10 + n))
        open_conflict(conn, aircraft_id, "LATE_2H", clock=lambda: T0)
    noise = [from_tower({"type": "NO_RUNWAY", "aircraft_id": aircraft_id}) for aircraft_id in ids] * 10
    sent = []
    start = time.perf_counter()
    tick(conn, get=lambda: noise, send=sent.append, clock=lambda: T0)
    elapsed = time.perf_counter() - start
    assert sorted(json.loads(raw)["aircraft_id"] for raw in sent) == ids   # every plane, exactly once
    assert elapsed < 0.5

