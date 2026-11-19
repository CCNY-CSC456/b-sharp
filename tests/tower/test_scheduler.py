# REQ-TOW-014, REQ-TOW-015
# Automated tests for the tower scheduler: the saved runway queue and radar's conflicts.
# These use the real schema / queries and the real messaging service on a throwaway messages.db.

import json
import sqlite3

import pytest

from src.tower.airport.airport_repo import RUNWAY_COUNT, create_airport, create_tables, get_conflicts
from src.tower.airport.runway_requests import (
    FREED, LANDED, NO_RUNWAY, REQUEST_LANDING, REQUEST_REFUSED, REQUEST_TAKEOFF, RUNWAY_ASSIGNED,
)
from src.tower.airport.scheduler import (
    CONFLICT, CONFLICT_RESOLVED, LATE_2_HOURS, LATE_4_HOURS, LOW_ON_GAS, TowerScheduler,
)
from src.tower.messaging import db as tower_db


@pytest.fixture(autouse=True)
def throwaway_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "messages.db"))
    tower_db.init_db()


@pytest.fixture
def tower():
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    return conn


def radar_sends(message_type, aircraft_id, timestamp, **extra):
    tower_db.save_message("radar", "tower", json.dumps(
        {"type": message_type, "aircraft_id": aircraft_id, "timestamp": timestamp, **extra}))


def conflict(aircraft_id, reason, timestamp):
    """Radar's CONFLICT message, exactly as radar's conflict_signals.py sends it."""
    radar_sends(CONFLICT, aircraft_id, timestamp, reason=reason)


def cycle(conn):
    return TowerScheduler(conn, "JFK").run_cycle()


def inbox(recipient):
    return [json.loads(m["content"]) for m in tower_db.get_messages(recipient)]


def of_type(recipient, kind):
    return [m for m in inbox(recipient) if m.get("type") == kind]


def fill_runways(conn):
    """Every runway taken, so later requests have to wait in the queue."""
    for n in range(RUNWAY_COUNT):
        radar_sends(REQUEST_LANDING, f"R{n}", "2026-11-19T08:00:00")
    cycle(conn)


def queue_with(conn, *planes, timestamp="2026-11-19T09:00:00"):
    fill_runways(conn)
    for plane in planes:
        radar_sends(REQUEST_LANDING, plane, timestamp)
    return cycle(conn).queued_requests


# --- the crash from PR 52 must not come back ---

def test_takeoff_before_landed_is_refused_and_the_scheduler_keeps_going(tower):
    radar_sends(REQUEST_LANDING, "A1", "2026-11-19T10:00:00")
    cycle(tower)
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-19T10:05:00")  # A1 hasn't reported LANDED
    radar_sends(REQUEST_LANDING, "B2", "2026-11-19T10:05:00")
    summary = cycle(tower)  # used to raise InvalidRunwayTransition, every cycle
    [refused] = of_type("radar", REQUEST_REFUSED)
    assert (refused["aircraft_id"], refused["phase"], refused["request"]) == ("A1", "LANDING_ASSIGNED", REQUEST_TAKEOFF)
    assert any(m["aircraft_id"] == "B2" for m in of_type("radar", RUNWAY_ASSIGNED))  # everyone else still answered
    assert "A1" not in summary.queued_requests  # refused requests leave the queue
    assert cycle(tower).request_replies == []   # and aren't tried again
    assert not any(m["type"] == REQUEST_REFUSED for m in inbox("command"))


# --- radar's CONFLICT messages ---

@pytest.mark.parametrize("reason, places", [(LATE_2_HOURS, 1), (LATE_4_HOURS, 2), (LOW_ON_GAS, 3)])
def test_each_reason_moves_the_plane_up_the_right_amount(tower, reason, places):
    queue_with(tower, "Q1", "Q2", "Q3", "Q4", "Q5")
    conflict("Q5", reason, "2026-11-19T09:10:00")
    queue = cycle(tower).queued_requests
    assert queue.index("Q5") == 4 - places


def test_repeats_every_second_count_once(tower):
    queue_with(tower, "Q1", "Q2", "Q3", "Q4", "Q5")
    for second in range(5):  # radar sends it every second until it hears CONFLICT_RESOLVED
        conflict("Q5", LATE_2_HOURS, f"2026-11-19T09:10:0{second}")
        cycle(tower)
    assert cycle(tower).queued_requests == ["Q1", "Q2", "Q3", "Q5", "Q4"]  # moved 1 place, not 5
    assert len(get_conflicts(tower, "JFK")) == 1


def test_radar_and_command_get_each_message_once(tower):
    queue_with(tower, "Q1", "Q2")
    for second in range(3):
        conflict("Q2", LOW_ON_GAS, f"2026-11-19T09:10:0{second}")
        cycle(tower)
    [to_radar] = of_type("radar", CONFLICT_RESOLVED)
    [alert] = of_type("command", CONFLICT)
    [cleared] = of_type("command", CONFLICT_RESOLVED)
    assert alert == {"type": CONFLICT, "conflict_id": 1, "severity": 2, "aircraft_id": "Q2",
                     "reason": LOW_ON_GAS, "timestamp": "2026-11-19T09:10:00"}
    assert {k: v for k, v in to_radar.items() if k != "timestamp"} == {
        "type": CONFLICT_RESOLVED, "conflict_id": 1, "aircraft_id": "Q2", "reason": LOW_ON_GAS, "queue_position": 1}
    assert cleared == {**to_radar, "severity": 2}


def test_radar_can_recognise_the_resolved_message(tower):
    # Radar's current code stops sending when it sees type CONFLICT_RESOLVED for its aircraft_id.
    queue_with(tower, "Q1")
    conflict("Q1", LATE_2_HOURS, "2026-11-19T09:10:00")
    cycle(tower)
    assert any(m["type"] == CONFLICT_RESOLVED and m["aircraft_id"] == "Q1" for m in inbox("radar"))


def test_late_4_hours_after_late_2_hours_is_2_places_in_total(tower):
    queue_with(tower, "Q1", "Q2", "Q3", "Q4", "Q5")
    conflict("Q5", LATE_2_HOURS, "2026-11-19T09:10:00")
    cycle(tower)
    conflict("Q5", LATE_4_HOURS, "2026-11-19T10:10:00")
    assert cycle(tower).queued_requests.index("Q5") == 2  # 4 -> 3 -> 2, not 4 -> 3 -> 1


def test_low_on_gas_adds_to_being_late(tower):
    queue_with(tower, "Q1", "Q2", "Q3", "Q4", "Q5")
    conflict("Q5", LATE_2_HOURS, "2026-11-19T09:10:00")
    conflict("Q5", LOW_ON_GAS, "2026-11-19T09:10:00")
    assert cycle(tower).queued_requests.index("Q5") == 0  # 1 + 3 places, clamped at the front


def test_conflict_before_the_plane_asks_waits_until_it_joins_the_queue(tower):
    queue_with(tower, "Q1", "Q2", "Q3")
    conflict("Q4", LOW_ON_GAS, "2026-11-19T09:10:00")
    cycle(tower)
    assert of_type("radar", CONFLICT_RESOLVED) == []         # not resolved yet: radar keeps sending
    assert [c["status"] for c in get_conflicts(tower, "JFK")] == ["PENDING"]
    radar_sends(REQUEST_LANDING, "Q4", "2026-11-19T09:20:00")
    assert cycle(tower).queued_requests == ["Q4", "Q1", "Q2", "Q3"]
    assert [m["aircraft_id"] for m in of_type("radar", CONFLICT_RESOLVED)] == ["Q4"]


def test_conflict_for_a_plane_with_a_runway_has_nothing_to_move(tower):
    radar_sends(REQUEST_LANDING, "A1", "2026-11-19T10:00:00")
    cycle(tower)
    conflict("A1", LOW_ON_GAS, "2026-11-19T10:01:00")
    cycle(tower)
    [resolved] = of_type("radar", CONFLICT_RESOLVED)
    assert resolved["queue_position"] is None


def test_same_reason_on_a_later_flight_is_a_new_conflict(tower):
    queue_with(tower, "Q1", "Q2")
    conflict("Q2", LOW_ON_GAS, "2026-11-19T09:10:00")
    cycle(tower)
    radar_sends("DEPARTED", "Q2", "2026-11-19T09:30:00")
    cycle(tower)
    radar_sends(REQUEST_LANDING, "Q2", "2026-11-19T12:00:00")
    conflict("Q2", LOW_ON_GAS, "2026-11-19T12:01:00")
    cycle(tower)
    assert [c["first_reported_at"] for c in get_conflicts(tower, "JFK")] == ["2026-11-19T09:10:00",
                                                                           "2026-11-19T12:01:00"]


def test_unknown_reasons_are_ignored(tower):
    queue_with(tower, "Q1", "Q2")
    conflict("Q2", "low on gas", "2026-11-19T09:10:00")  # wrong capitals: radar's exact strings only
    radar_sends("PRIORITY_HIGH", "Q2", "2026-11-19T09:10:00")
    assert cycle(tower).queued_requests == ["Q1", "Q2"]
    assert get_conflicts(tower, "JFK") == []


# --- the queue ---

def test_waiting_planes_are_told_no_runway_once(tower):
    queue_with(tower, "Q1")
    cycle(tower)
    cycle(tower)
    assert [m["aircraft_id"] for m in of_type("radar", NO_RUNWAY)] == ["Q1"]
    assert [m["aircraft_id"] for m in of_type("command", NO_RUNWAY)] == ["Q1"]  # REQ-TOW-012 still holds


def test_first_come_first_served_within_one_cycle(tower):
    fill_runways(tower)
    radar_sends(REQUEST_LANDING, "LATE", "2026-11-19T09:05:00")   # in the inbox first, but asked later
    radar_sends(REQUEST_LANDING, "EARLY", "2026-11-19T09:00:00")
    assert cycle(tower).queued_requests == ["EARLY", "LATE"]


def test_freed_runway_goes_to_the_front_of_the_queue(tower):
    queue_with(tower, "Q1", "Q2")
    radar_sends("DEPARTED", "R3", "2026-11-19T09:30:00")
    summary = cycle(tower)
    assert summary.queued_requests == ["Q2"]
    assert [(m["aircraft_id"], m["runway_id"]) for m in of_type("radar", RUNWAY_ASSIGNED)][-1] == ("Q1", 4)


def test_freed_is_not_sent_to_command(tower):
    radar_sends(REQUEST_LANDING, "A1", "2026-11-19T10:00:00")
    cycle(tower)
    radar_sends(LANDED, "A1", "2026-11-19T10:05:00")
    radar_sends("PARKED", "A1", "2026-11-19T10:06:00")
    cycle(tower)
    assert not any(m["type"] == FREED for m in inbox("command"))


# --- the shared messages.db ---

def test_a_messages_db_made_by_older_code_still_works(tmp_path, monkeypatch):
    old = tmp_path / "old_messages.db"
    conn = sqlite3.connect(old)  # the table exactly as the old db.py created it
    conn.execute("CREATE TABLE messages (sender TEXT, recipient TEXT, content TEXT, "
                 "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO messages (sender, recipient, content) VALUES ('radar', 'tower', 'hello')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(tower_db, "DB", str(old))
    tower_db.save_message("radar", "tower", "again")  # used to fail: no column named kind
    assert [m["content"] for m in tower_db.get_messages("tower")] == ["hello", "again"]


def test_same_timestamp_keeps_the_order_radar_sent_them(tower):
    fill_runways(tower)
    for plane in ("ZULU", "ALPHA", "MIKE"):  # not alphabetical on purpose
        radar_sends(REQUEST_LANDING, plane, "2026-11-19T09:00:00")
    assert cycle(tower).queued_requests == ["ZULU", "ALPHA", "MIKE"]


# --- LANDED / PARKED / DEPARTED are applied even when a request arrives in the same cycle ---

def test_landed_then_takeoff_in_one_cycle_clears_for_takeoff(tower):
    radar_sends(REQUEST_LANDING, "A1", "2026-11-19T10:00:00")
    cycle(tower)
    radar_sends(LANDED, "A1", "2026-11-19T10:05:00")          # both arrive before tower runs again
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-19T10:06:00")
    cycle(tower)
    assert of_type("radar", REQUEST_REFUSED) == []
    [cleared] = [m for m in of_type("radar", RUNWAY_ASSIGNED) if m["request"] == REQUEST_TAKEOFF]
    assert cleared["runway_id"] == 1
    assert any(m["type"] == "AIRCRAFT_LANDED" for m in inbox("command"))  # command still hears it landed


def test_parked_then_takeoff_in_one_cycle(tower):
    radar_sends(REQUEST_LANDING, "A1", "2026-11-19T10:00:00")
    cycle(tower)
    radar_sends(LANDED, "A1", "2026-11-19T10:05:00")
    radar_sends("PARKED", "A1", "2026-11-19T10:06:00")
    radar_sends(REQUEST_TAKEOFF, "A1", "2026-11-19T10:30:00")
    cycle(tower)
    assert [m["request"] for m in of_type("radar", RUNWAY_ASSIGNED)] == [REQUEST_LANDING, REQUEST_TAKEOFF]


def test_old_history_is_not_replayed(tower):
    # A LANDED from before the last handled message is history: it must not touch the new landing clearance.
    radar_sends(REQUEST_LANDING, "A1", "2026-11-19T10:00:00")
    radar_sends(LANDED, "A1", "2026-11-19T10:05:00")
    radar_sends("DEPARTED", "A1", "2026-11-19T10:30:00")
    radar_sends(REQUEST_LANDING, "A1", "2026-11-19T12:00:00")
    cycle(tower)
    cycle(tower)
    phase = tower.execute("SELECT status FROM runway_assignments WHERE aircraft_id = 'A1'").fetchone()
    assert phase == ("LANDING_ASSIGNED",)

