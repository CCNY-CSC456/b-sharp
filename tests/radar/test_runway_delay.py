# REQ-RAD-019
# Automated tests for the 30 second wait between a runway assignment and LANDED/PARKED or DEPARTED.
# CI runs these with: pytest tests/radar
# Every test uses an in-memory database and fake messaging, so tower doesn't need to run.

import json
from datetime import datetime, timedelta

from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.runway_delay import RUNWAY_DELAY_SECONDS, apply_runway_assignments, finish_due_runways
from src.radar.airplane.runway_requests import report_parked

MEM = ":memory:"
OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)
T0 = datetime(2026, 11, 19, 14, 0, 0)


def at(seconds):
    return lambda: T0 + timedelta(seconds=seconds)


def plane(aircraft_id="AA123", status="Landing", altitude=2000):
    return AircraftTelemetry(aircraft_id=aircraft_id, latitude=40.64, longitude=-73.78, altitude=altitude,
                             status=status, timestamp=OLD_TIME)


def assigned(aircraft_id="AA123", runway_id="R1", request="REQUEST_LANDING", request_timestamp="2026-11-19T13:59:58"):
    """Exactly what tower sends (REQ-TOW-011)."""
    return {"sender": "tower", "recipient": "radar", "content": json.dumps(
        {"type": "RUNWAY_ASSIGNED", "aircraft_id": aircraft_id, "runway_id": runway_id,
         "request": request, "request_timestamp": request_timestamp})}


def setup(*planes):
    conn = init_db(MEM)
    for p in planes or (plane(),):
        create_aircraft(conn, p)
    return conn


def types(sent):
    return [json.loads(raw)["type"] for raw in sent]


def test_the_delay_is_30_seconds():
    assert RUNWAY_DELAY_SECONDS == 30


def test_assignment_saves_the_runway_and_starts_the_wait():
    conn = setup()
    results = apply_runway_assignments(conn, [assigned()], clock=at(0))
    assert results == ["AA123: runway R1 assigned, landing in 30s"]
    assert get_aircraft(conn, "AA123").runway_id == "R1"


def test_nothing_is_sent_before_30_seconds():
    conn = setup()
    apply_runway_assignments(conn, [assigned()], clock=at(0))
    sent = []
    assert finish_due_runways(conn, send=sent.append, clock=at(29)) == []
    assert sent == []


def test_landing_plane_lands_and_parks_after_30_seconds():
    conn = setup()
    apply_runway_assignments(conn, [assigned()], clock=at(0))
    sent = []
    results = finish_due_runways(conn, send=sent.append, clock=at(30))
    assert results == ["AA123: landed on runway R1 and parked (runway available)"]
    # LANDED, then PARKED (tower frees the runway on PARKED, REQ-TOW-011), then the plane's new data.
    assert types(sent) == ["LANDED", "PARKED", "AIRCRAFT_INFO"]
    landed = get_aircraft(conn, "AA123")
    assert landed.status == "Parked"
    assert landed.altitude == 0
    assert landed.runway_id is None
    assert json.loads(sent[2])["status"] == "Parked"


def test_departing_plane_departs_after_30_seconds():
    conn = setup(plane(status="Departing", altitude=0))
    apply_runway_assignments(conn, [assigned(request="REQUEST_TAKEOFF")], clock=at(0))
    sent = []
    results = finish_due_runways(conn, send=sent.append, clock=at(31))
    assert results == ["AA123: departed from runway R1 (runway available)"]
    assert types(sent) == ["DEPARTED"]
    assert get_aircraft(conn, "AA123").runway_id is None


def test_each_assignment_finishes_once():
    conn = setup()
    inbox = [assigned()]
    apply_runway_assignments(conn, inbox, clock=at(0))
    sent = []
    finish_due_runways(conn, send=sent.append, clock=at(30))
    # The same reply is still in the inbox on the next run; it must not start a new wait.
    assert apply_runway_assignments(conn, inbox, clock=at(31)) == []
    assert finish_due_runways(conn, send=sent.append, clock=at(90)) == []
    assert len(sent) == 3


def test_a_new_assignment_of_the_same_runway_starts_a_new_wait():
    # Land on R1, then ask to take off and get R1 again: a different request, so a different reply.
    conn = setup()
    landing = assigned(request="REQUEST_LANDING", request_timestamp="2026-11-19T13:59:00")
    apply_runway_assignments(conn, [landing], clock=at(0))
    finish_due_runways(conn, send=lambda raw: None, clock=at(30))
    takeoff = assigned(request="REQUEST_TAKEOFF", request_timestamp="2026-11-19T14:01:00")
    assert apply_runway_assignments(conn, [landing, takeoff], clock=at(60)) == [
        "AA123: runway R1 assigned, departing in 30s"]
    sent = []
    finish_due_runways(conn, send=sent.append, clock=at(90))
    assert types(sent) == ["DEPARTED"]


def test_reply_without_request_uses_the_planes_status():
    # fake-tower-reply doesn't say which request it answers.
    conn = setup(plane(status="Departing", altitude=0))
    reply = {"sender": "tower", "recipient": "radar",
             "content": json.dumps({"type": "RUNWAY_ASSIGNED", "aircraft_id": "AA123", "runway_id": "R2"})}
    assert apply_runway_assignments(conn, [reply], clock=at(0)) == ["AA123: runway R2 assigned, departing in 30s"]


def test_many_planes_each_wait_their_own_30_seconds():
    conn = setup(plane("A1"), plane("B2"))
    apply_runway_assignments(conn, [assigned("A1", "R1")], clock=at(0))
    apply_runway_assignments(conn, [assigned("A1", "R1"), assigned("B2", "R2")], clock=at(10))
    sent = []
    finish_due_runways(conn, send=sent.append, clock=at(30))
    assert {json.loads(raw)["aircraft_id"] for raw in sent} == {"A1"}
    finish_due_runways(conn, send=sent.append, clock=at(40))
    assert {json.loads(raw)["aircraft_id"] for raw in sent} == {"A1", "B2"}


def test_ignores_no_runway_refused_unknown_planes_and_other_senders():
    conn = setup()
    inbox = [
        {"sender": "tower", "recipient": "radar", "content": json.dumps({"type": "NO_RUNWAY", "aircraft_id": "AA123"})},
        {"sender": "tower", "recipient": "radar", "content": json.dumps(
            {"type": "REQUEST_REFUSED", "aircraft_id": "AA123", "phase": "LANDING_ASSIGNED"})},
        {"sender": "tower", "recipient": "radar", "content": json.dumps(
            {"type": "RUNWAY_ASSIGNED", "aircraft_id": "AA123", "runway_id": None})},
        assigned(aircraft_id="ZZ9"),
        {**assigned(), "sender": "command"},
        {"sender": "tower", "recipient": "radar", "content": "not json"},
    ]
    assert apply_runway_assignments(conn, inbox, clock=at(0)) == []
    assert finish_due_runways(conn, send=lambda raw: None, clock=at(100)) == []


# --- PARKED (tower frees a landed plane's runway on PARKED, REQ-TOW-011; radar never sent it before) ---

def test_report_parked_sends_parked():
    conn = setup()
    sent = []
    message = report_parked(conn, "AA123", send=sent.append)
    assert message["type"] == "PARKED"
    assert json.loads(sent[0])["aircraft_id"] == "AA123"
