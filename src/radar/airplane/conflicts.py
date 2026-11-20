# REQ-RAD-018
# conflicts.py — tell tower about a plane that is late or low on gas, every second, until tower resolves it.
#
# Matches tower's REQ-TOW-015 exactly:
# radar -> tower:  {"type": "CONFLICT", "aircraft_id": "A1", "reason": "Low on Gas", "timestamp": "...",
#                   "warning": "A1 is low on fuel (non-emergency)"}
#                  sent once per second (by the run loop, monitor.py) while the conflict is OPEN.
#                  reason must be tower's exact text; warning is extra (tower ignores it) so it's never just a flag.
# tower -> radar:  {"type": "CONFLICT_RESOLVED", "conflict_id": 3, "aircraft_id": "A1", "reason": "Low on Gas",
#                   "queue_position": 1, "timestamp": "..."}
#                  radar marks its OPEN conflict for that plane + reason RESOLVED, updates the plane,
#                  sends tower AIRCRAFT_INFO, and stops sending.
#
# Tower counts plane + reason as ONE conflict until the plane departs, so radar refuses to report the same
# reason twice in one flight (tower would never answer the second one).
# Opening a conflict does not block: it is saved in radar.db, so many planes can have conflicts at once.

import json

from src.radar.airplane.aircraft_repo import (
    TIME_FORMAT, close_conflict, get_aircraft, insert_conflict, is_handled, latest_flight_conflict, mark_handled,
    now, select_conflicts, touch_aircraft,
)
from src.radar.airplane.runway_requests import send_aircraft_info, send_as_tower, send_to_tower
from src.radar.airplane.tower_inbox import from_tower

CONFLICT = "CONFLICT"                    # radar -> tower
CONFLICT_RESOLVED = "CONFLICT_RESOLVED"  # tower -> radar

# reason code (what radar stores and the CLI shows) -> the warning sentence.
# Tower moves the plane up the queue 1 / 2 / 3 places for these. None of them are emergencies.
CONFLICT_REASONS = {
    "LATE_2H":  "is running 2+ hours late",
    "LATE_4H":  "is running 4+ hours late",
    "LOW_FUEL": "is low on fuel (non-emergency)",
}

# reason code -> tower's exact text (REQ-TOW-015). Tower ignores any other text.
REASON_TEXT = {
    "LATE_2H":  "Late by +2 hour",
    "LATE_4H":  "Late by +4 hour",
    "LOW_FUEL": "Low on Gas",
}
REASON_CODE = {text: code for code, text in REASON_TEXT.items()}


def open_conflict(conn, aircraft_id, reason, clock=now):
    """Start sending a conflict for this plane. Returns it as a dict.

    Raises ValueError for an unknown plane or reason, or a reason already reported this flight.
    """
    if reason not in CONFLICT_REASONS:
        raise ValueError(f"unknown conflict reason {reason!r}, use one of: {', '.join(CONFLICT_REASONS)}")
    if get_aircraft(conn, aircraft_id) is None:
        raise ValueError(f"aircraft {aircraft_id} does not exist")
    status = latest_flight_conflict(conn, aircraft_id, reason)
    if status == "OPEN":
        raise ValueError(f"aircraft {aircraft_id} already has an open {reason} conflict")
    if status == "RESOLVED":
        raise ValueError(f"aircraft {aircraft_id} already reported {reason} for this flight "
                         "(tower counts it once until the plane departs)")
    opened_at = clock().strftime(TIME_FORMAT)
    conflict_id = f"{aircraft_id}-{reason}-{opened_at}"   # radar's own ID, e.g. "AA123-LOW_FUEL-2026-11-19T14:00:00"
    insert_conflict(conn, conflict_id, aircraft_id, reason, opened_at)
    return get_conflict(conn, conflict_id)


def get_conflict(conn, conflict_id):
    return next((c for c in select_conflicts(conn) if c["conflict_id"] == conflict_id), None)


def get_conflicts(conn, status=None):
    """Every conflict, or only "OPEN" / "RESOLVED" ones, oldest first."""
    return select_conflicts(conn, status)


def conflict_message(conflict, clock=now):
    return {"type": CONFLICT, "aircraft_id": conflict["aircraft_id"], "reason": REASON_TEXT[conflict["reason"]],
            "timestamp": clock().strftime(TIME_FORMAT),
            "warning": f"{conflict['aircraft_id']} {CONFLICT_REASONS[conflict['reason']]}"}


def send_open_conflicts(conn, send=send_to_tower, clock=now):
    """Send one CONFLICT for every OPEN conflict. Returns the messages sent, as dicts."""
    sent = []
    for conflict in get_conflicts(conn, "OPEN"):
        message = conflict_message(conflict, clock)
        send(json.dumps(message))
        sent.append(message)
    return sent


def apply_conflict_resolutions(conn, inbox, send=send_to_tower, clock=now):
    """Close the OPEN conflict each new CONFLICT_RESOLVED names (plane + reason). Returns what happened, as text.

    Each tower message is used once, even if nothing matched, so an old reply still in the inbox
    can never close a conflict opened later.
    """
    results = []
    for data in from_tower(inbox, CONFLICT_RESOLVED):
        aircraft_id, code = data.get("aircraft_id"), REASON_CODE.get(data.get("reason"))
        if not isinstance(aircraft_id, str) or code is None:
            continue
        key = f"{CONFLICT_RESOLVED}:{data.get('conflict_id')}:{aircraft_id}:{data.get('reason')}:{data.get('timestamp')}"
        if is_handled(conn, key):
            continue
        mark_handled(conn, key)
        conflict = next((c for c in get_conflicts(conn, "OPEN")
                         if c["aircraft_id"] == aircraft_id and c["reason"] == code), None)
        if conflict is None or not close_conflict(conn, conflict["conflict_id"], aircraft_id,
                                                  clock().strftime(TIME_FORMAT)):
            continue
        if get_aircraft(conn, aircraft_id) is not None:   # the plane may have been deleted since
            touch_aircraft(conn, aircraft_id, clock=clock)
            send_aircraft_info(conn, aircraft_id, send=send)
        position = data.get("queue_position")
        where = f" (queue position {position})" if position is not None else ""
        results.append(f"{aircraft_id}: conflict {code} resolved by tower{where}")
    return results


def fake_conflict_resolved(conflict, send=send_as_tower, clock=now):
    """TESTING ONLY: send radar a CONFLICT_RESOLVED as if tower sent it. Returns it as a dict."""
    stamp = clock()
    reply = {"type": CONFLICT_RESOLVED, "conflict_id": int(stamp.timestamp()), "aircraft_id": conflict["aircraft_id"],
             "reason": REASON_TEXT[conflict["reason"]], "queue_position": None,
             "timestamp": stamp.strftime(TIME_FORMAT)}
    send(json.dumps(reply))
    return reply
