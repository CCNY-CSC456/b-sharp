# REQ-RAD-018
# Automated tests for radar's conflict signals (late +2h, late +4h, low on gas). CI runs these with: pytest tests/radar
# Every test uses an in-memory database and fake messaging, so tower doesn't need to run.
# The messages match tower's REQ-TOW-015 exactly.

import json
from datetime import datetime, timedelta

import pytest

from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db
from src.radar.airplane.conflicts import (
    CONFLICT_REASONS, REASON_TEXT, apply_conflict_resolutions, get_conflicts, open_conflict, send_open_conflicts,
)
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.runway_requests import report_departed

MEM = ":memory:"
OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)
NOW = datetime(2026, 11, 19, 14, 0, 0)


def plane(aircraft_id="AA123"):
    return AircraftTelemetry(aircraft_id=aircraft_id, latitude=40.77, longitude=-73.87, altitude=2000,
                             status="Landing", timestamp=OLD_TIME)


def setup(*ids):
    conn = init_db(MEM)
    for aircraft_id in ids or ("AA123",):
        create_aircraft(conn, plane(aircraft_id))
    return conn


def from_tower(payload):
    return {"sender": "tower", "recipient": "radar", "content": json.dumps(payload)}


def resolved(reason="Low on Gas", aircraft_id="AA123", conflict_id=3, timestamp="2026-11-19T14:00:05"):
    """Exactly what tower sends (REQ-TOW-015)."""
    return from_tower({"type": "CONFLICT_RESOLVED", "conflict_id": conflict_id, "aircraft_id": aircraft_id,
                       "reason": reason, "queue_position": 1, "timestamp": timestamp})


# --- opening a conflict ---

def test_the_three_reasons_and_towers_exact_text():
    assert set(CONFLICT_REASONS) == {"LATE_2H", "LATE_4H", "LOW_FUEL"}
    assert REASON_TEXT == {"LATE_2H": "Late by +2 hour", "LATE_4H": "Late by +4 hour", "LOW_FUEL": "Low on Gas"}


def test_open_conflict_records_it():
    conn = setup()
    conflict = open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW)
    assert conflict["aircraft_id"] == "AA123"
    assert conflict["reason"] == "LOW_FUEL"
    assert conflict["status"] == "OPEN"
    assert get_conflicts(conn) == [conflict]


def test_open_conflict_rejects_unknown_plane_and_reason():
    conn = setup()
    with pytest.raises(ValueError, match="does not exist"):
        open_conflict(conn, "NOPE", "LOW_FUEL")
    with pytest.raises(ValueError, match="reason"):
        open_conflict(conn, "AA123", "BORED")
    assert get_conflicts(conn) == []


def test_same_reason_twice_while_open_is_refused():
    conn = setup()
    open_conflict(conn, "AA123", "LATE_2H", clock=lambda: NOW)
    with pytest.raises(ValueError, match="already has an open"):
        open_conflict(conn, "AA123", "LATE_2H", clock=lambda: NOW)


def test_a_plane_can_have_different_reasons_open():
    conn = setup()
    open_conflict(conn, "AA123", "LATE_2H", clock=lambda: NOW)
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW)
    assert len(get_conflicts(conn, status="OPEN")) == 2


def test_same_reason_again_this_flight_is_refused_but_allowed_after_departing():
    # Tower: plane + reason is ONE conflict until the plane departs, so a repeat would never be answered.
    conn = setup()
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW)
    apply_conflict_resolutions(conn, [resolved()], send=lambda raw: None, clock=lambda: NOW)
    with pytest.raises(ValueError, match="already reported LOW_FUEL for this flight"):
        open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW + timedelta(seconds=5))
    report_departed(conn, "AA123", send=lambda raw: None, clock=lambda: NOW + timedelta(seconds=10))
    again = open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW + timedelta(seconds=20))
    assert again["status"] == "OPEN"


# --- sending (once per call; the run loop calls it every second) ---

def test_send_matches_towers_conflict_message():
    conn = setup()
    open_conflict(conn, "AA123", "LATE_4H", clock=lambda: OLD_TIME)
    sent = []
    send_open_conflicts(conn, send=sent.append, clock=lambda: NOW)
    message = json.loads(sent[0])
    assert message["type"] == "CONFLICT"
    assert message["aircraft_id"] == "AA123"
    assert message["reason"] == "Late by +4 hour"                     # tower ignores any other text
    assert message["timestamp"] == "2026-11-19T14:00:00"              # when this copy was sent
    assert message["warning"] == "AA123 is running 4+ hours late"     # AC: no binary-only outputs


def test_send_repeats_every_call_until_resolved():
    conn = setup()
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW)
    sent = []
    for second in range(3):
        send_open_conflicts(conn, send=sent.append, clock=lambda: NOW + timedelta(seconds=second))
    assert [json.loads(raw)["timestamp"] for raw in sent] == [
        "2026-11-19T14:00:00", "2026-11-19T14:00:01", "2026-11-19T14:00:02"]
    apply_conflict_resolutions(conn, [resolved()], send=lambda raw: None, clock=lambda: NOW)
    send_open_conflicts(conn, send=sent.append, clock=lambda: NOW)
    assert len(sent) == 3   # stopped


def test_send_one_message_per_open_conflict_for_many_planes():
    ids = [f"P{n}" for n in range(50)]
    conn = setup(*ids)
    for aircraft_id in ids:
        open_conflict(conn, aircraft_id, "LATE_2H", clock=lambda: NOW)
    sent = []
    send_open_conflicts(conn, send=sent.append, clock=lambda: NOW)
    assert sorted(json.loads(raw)["aircraft_id"] for raw in sent) == sorted(ids)


# --- tower's CONFLICT_RESOLVED ---

def test_resolution_closes_the_conflict_and_updates_the_plane():
    conn = setup()
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: OLD_TIME)
    sent = []
    results = apply_conflict_resolutions(conn, [resolved()], send=sent.append, clock=lambda: NOW)
    assert results == ["AA123: conflict LOW_FUEL resolved by tower (queue position 1)"]
    [closed] = get_conflicts(conn)
    assert closed["status"] == "RESOLVED"
    assert closed["resolved_at"] == "2026-11-19T14:00:00"
    assert get_aircraft(conn, "AA123").timestamp == NOW       # "Update Aircraft data"
    assert json.loads(sent[0])["type"] == "AIRCRAFT_INFO"     # tower gets the updated plane


def test_resolution_only_closes_the_matching_reason():
    conn = setup()
    open_conflict(conn, "AA123", "LATE_2H", clock=lambda: NOW)
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW)
    apply_conflict_resolutions(conn, [resolved("Late by +2 hour")], send=lambda raw: None, clock=lambda: NOW)
    assert [c["reason"] for c in get_conflicts(conn, status="OPEN")] == ["LOW_FUEL"]


def test_each_resolution_is_applied_once():
    conn = setup()
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW)
    inbox = [resolved()]
    apply_conflict_resolutions(conn, inbox, send=lambda raw: None, clock=lambda: NOW)
    assert apply_conflict_resolutions(conn, inbox, send=lambda raw: None, clock=lambda: NOW) == []


def test_an_old_resolution_does_not_close_a_new_conflict():
    # The inbox keeps every message, so a CONFLICT_RESOLVED from an earlier flight is still there.
    conn = setup()
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: OLD_TIME)
    inbox = [resolved(conflict_id=3)]
    apply_conflict_resolutions(conn, inbox, send=lambda raw: None, clock=lambda: OLD_TIME)
    report_departed(conn, "AA123", send=lambda raw: None, clock=lambda: NOW)
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW + timedelta(seconds=1))
    apply_conflict_resolutions(conn, inbox, send=lambda raw: None, clock=lambda: NOW + timedelta(seconds=2))
    assert [c["status"] for c in get_conflicts(conn, status="OPEN")] == ["OPEN"]
    # tower's answer to the NEW conflict (a new conflict_id) does close it
    inbox.append(resolved(conflict_id=4, timestamp="2026-11-19T14:00:09"))
    apply_conflict_resolutions(conn, inbox, send=lambda raw: None, clock=lambda: NOW + timedelta(seconds=9))
    assert get_conflicts(conn, status="OPEN") == []


def test_resolution_ignores_bad_or_mismatched_messages():
    conn = setup("AA123", "BB456")
    open_conflict(conn, "AA123", "LOW_FUEL", clock=lambda: NOW)
    inbox = [
        resolved(aircraft_id="BB456"),                     # wrong plane
        resolved(reason="Late by +2 hour"),                # wrong reason
        resolved(reason="LOW_FUEL"),                       # radar's code, not tower's text
        {**resolved(), "sender": "command"},               # only tower resolves
        {"sender": "tower", "recipient": "radar", "content": "hello"},
    ]
    assert apply_conflict_resolutions(conn, inbox, send=lambda raw: None, clock=lambda: NOW) == []
    assert get_conflicts(conn)[0]["status"] == "OPEN"
