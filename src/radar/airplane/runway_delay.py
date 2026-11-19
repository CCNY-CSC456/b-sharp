# REQ-RAD-019
# runway_delay.py — a plane uses its runway for 30 seconds before the runway is available again.
#
# tower -> radar:  RUNWAY_ASSIGNED {aircraft_id, runway_id, request, request_timestamp}   (exists, REQ-TOW-011)
# radar waits RUNWAY_DELAY_SECONDS, then:
#   landing plane:   LANDED, then PARKED (tower frees the runway on PARKED), then AIRCRAFT_INFO (now Parked, altitude 0)
#   departing plane: DEPARTED (tower frees the runway)
#
# The wait is saved in radar.db (runway_timers), so many planes can wait at once and nothing blocks.
# Each RUNWAY_ASSIGNED is handled once: it is named by the request it answers, so getting the same
# runway again for a NEW request starts a new wait.

import json

from src.radar.airplane.aircraft_repo import (
    TIME_FORMAT, clear_runway, finish_runway_timer, get_aircraft, insert_runway_timer, now,
    select_due_timers, update_landed, update_runway,
)
from src.radar.airplane.runway_requests import (
    REQUEST_LANDING, REQUEST_TAKEOFF, RUNWAY_ASSIGNED, report_departed, report_landed, report_parked,
    send_aircraft_info, send_to_tower,
)
from src.radar.airplane.tower_inbox import from_tower

from datetime import timedelta

RUNWAY_DELAY_SECONDS = 30


def apply_runway_assignments(conn, inbox, clock=now):
    """Save each new runway tower assigned and start its 30 second wait. Returns what happened, as text."""
    results = []
    for data in from_tower(inbox, RUNWAY_ASSIGNED):
        aircraft_id, runway_id = data.get("aircraft_id"), data.get("runway_id")
        if not isinstance(aircraft_id, str) or runway_id is None:
            continue
        plane = get_aircraft(conn, aircraft_id)
        if plane is None:
            continue
        runway_id = str(runway_id)  # tower may send "R1" or 3; keep it as text (same as check_tower_replies)
        request = data.get("request")
        if request not in (REQUEST_LANDING, REQUEST_TAKEOFF):
            # fake-tower-reply doesn't say; a Landing plane asked to land, anything else to take off.
            request = REQUEST_LANDING if plane.status == "Landing" else REQUEST_TAKEOFF
        key = f"{RUNWAY_ASSIGNED}:{aircraft_id}:{runway_id}:{request}:{data.get('request_timestamp')}"
        if not insert_runway_timer(conn, key, aircraft_id, runway_id, request, clock().strftime(TIME_FORMAT)):
            continue  # this reply already started its wait
        if plane.runway_id != runway_id:
            update_runway(conn, aircraft_id, runway_id)
        how = "landing" if request == REQUEST_LANDING else "departing"
        results.append(f"{aircraft_id}: runway {runway_id} assigned, {how} in {RUNWAY_DELAY_SECONDS}s")
    return results


def finish_due_runways(conn, send=send_to_tower, clock=now):
    """Land/park or depart every plane whose 30 seconds are up. Returns what happened, as text."""
    cutoff = (clock() - timedelta(seconds=RUNWAY_DELAY_SECONDS)).strftime(TIME_FORMAT)
    results = []
    for timer in select_due_timers(conn, cutoff):
        aircraft_id, runway_id = timer["aircraft_id"], timer["runway_id"]
        finish_runway_timer(conn, timer["timer_key"])
        if get_aircraft(conn, aircraft_id) is None:   # deleted while it waited
            continue
        if timer["request"] == REQUEST_LANDING:
            report_landed(conn, aircraft_id, send=send)
            report_parked(conn, aircraft_id, send=send)
            update_landed(conn, aircraft_id, clock=clock)
            send_aircraft_info(conn, aircraft_id, send=send)
            results.append(f"{aircraft_id}: landed on runway {runway_id} and parked (runway available)")
        else:
            report_departed(conn, aircraft_id, send=send, clock=clock)
            clear_runway(conn, aircraft_id, clock=clock)
            results.append(f"{aircraft_id}: departed from runway {runway_id} (runway available)")
    return results
