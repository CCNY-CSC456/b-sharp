# REQ-TOW-014, REQ-TOW-015
# scheduler.py — one tower cycle: separation, a saved first-come-first-served runway queue, and radar's conflicts.
#
# Each cycle, in order:
#   1. separation (REQ-TOW-013); planes being moved can't get a runway until their move is done,
#   2. LANDED / PARKED / DEPARTED (the plane leaves the queue; PARKED and DEPARTED free its runway),
#   3. new runway requests join the back of the queue, oldest request first,
#   4. radar's CONFLICT messages move a queued plane up (Late by +2 hour: 1, Late by +4 hour: 2, Low on Gas: 3),
#   5. the queue is worked through in order: a free runway -> RUNWAY_ASSIGNED; none -> the plane waits
#      (radar and command are told NO_RUNWAY once); a request that doesn't fit the plane's phase -> REQUEST_REFUSED,
#   6. replies are sent (they go through runway_response_queue first, so a crash can't lose them),
#   7. positions and LANDED / PARKED / DEPARTED are forwarded to command (REQ-TOW-009).

from __future__ import annotations

from dataclasses import dataclass, field
import json
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.tower.airport.airport_repo import (
    InvalidRunwayTransition,
    assign_runway,
    enqueue_response,
    free_runway,
    get_assigned_runway,
    get_conflicts,
    get_request_queue,
    get_response_queue,
    is_processed,
    mark_processed,
    now,
    open_conflict,
    remove_queued_request,
    remove_queued_response,
    resolve_conflict,
    save_request_queue,
    set_assignment_status,
)
from src.tower.airport.runway_requests import (
    DEPARTED,
    FREED,
    LANDED,
    LANDED_PHASE,
    LANDING_ASSIGNED,
    NO_RUNWAY,
    PARKED,
    REQUEST_LANDING,
    REQUEST_TAKEOFF,
    RUNWAY_ASSIGNED,
    TAKEOFF_ASSIGNED,
    forward_positions,
    newest_per_plane,
    read_json,
    read_request,
    read_tower_inbox,
    refusal_reply,
    send_to_command,
    send_to_radar,
)
from src.tower.airport.separation import SeparationPass

# --- REQ-TOW-015: conflicts, exactly as radar sends them ---
CONFLICT = "CONFLICT"                    # radar -> tower (every second until resolved); tower -> command (once)
CONFLICT_RESOLVED = "CONFLICT_RESOLVED"  # tower -> radar (so it stops sending) and tower -> command (once each)
CONFLICT_SEVERITY = 2                    # command ranks unsafe separation (1) above conflicts (2)

LATE_2_HOURS = "Late by +2 hour"
LATE_4_HOURS = "Late by +4 hour"
LOW_ON_GAS = "Low on Gas"

# How many places a conflict moves the plane up the queue.
CONFLICT_SPOTS: Dict[str, int] = {LATE_2_HOURS: 1, LATE_4_HOURS: 2, LOW_ON_GAS: 3}
# Being late doesn't add up: "Late by +4 hour" after "Late by +2 hour" only moves the plane 1 more place (2 in total).
LATE_REASONS = (LATE_2_HOURS, LATE_4_HOURS)

PENDING, RESOLVED = "PENDING", "RESOLVED"


@dataclass
class QueuedRequest:
    aircraft_id: str
    req_type: str
    req_timestamp: Optional[str]
    msg_key: str


@dataclass(frozen=True)
class CycleSummary:
    """Result of a single integrated tower scheduling cycle."""

    separation_changes: List[Dict[str, Any]]
    request_replies: List[Dict[str, Any]]
    forwarded_messages: List[Dict[str, Any]]
    busy_aircraft: Set[str]
    queued_requests: List[str] = field(default_factory=list)
    queued_responses: List[Dict[str, Any]] = field(default_factory=list)
    conflict_changes: List[Dict[str, Any]] = field(default_factory=list)


def conflict_streaks(inbox: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, str, str]], Set[Tuple[str, str, str]]]:
    """Radar's CONFLICT messages grouped into conflicts, in the order radar first reported them.

    Radar repeats a conflict every second with a new timestamp, so a conflict is (aircraft_id, reason,
    timestamp of its FIRST message). Repeats of the same plane + reason are the same conflict, until the plane
    departs; after that the same reason is a new conflict (a new flight).
    Returns (every conflict, the ones from each plane's current flight).
    """
    current: Dict[Tuple[str, str], str] = {}
    streaks: List[Tuple[str, str, str]] = []
    for message in inbox:
        if message.get("sender") != "radar":
            continue
        data = read_json(message)
        if data is None or not isinstance(data.get("aircraft_id"), str):
            continue
        aircraft_id, kind = data["aircraft_id"], data.get("type")
        if kind == DEPARTED:
            current = {key: ts for key, ts in current.items() if key[0] != aircraft_id}
        elif kind == CONFLICT and data.get("reason") in CONFLICT_SPOTS:
            key = (aircraft_id, data["reason"])
            if key not in current:
                current[key] = data.get("timestamp") or ""
                streaks.append((aircraft_id, data["reason"], current[key]))
    return streaks, {(a, r, ts) for (a, r), ts in current.items()}


class TowerScheduler:
    """Coordinates separation, conflict reordering, and SQLite-persisted queues."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        airport_id: str,
        get_inbox: Callable[[], List[Dict[str, Any]]] = read_tower_inbox,
        to_radar: Callable[[str], None] = send_to_radar,
        to_command: Callable[[str], None] = send_to_command,
        spot_shifts: Optional[Dict[str, int]] = None,
    ) -> None:
        self.conn = conn
        self.airport_id = airport_id
        self.get_inbox = get_inbox
        self.to_radar = to_radar
        self.to_command = to_command
        self.spot_shifts = spot_shifts or dict(CONFLICT_SPOTS)
        self.request_queue: List[QueuedRequest] = []
        self.conflict_changes: List[Dict[str, Any]] = []

    # --- the saved queue ---

    def _load_request_queue(self) -> None:
        rows = get_request_queue(self.conn, self.airport_id)
        self.request_queue = [
            QueuedRequest(
                aircraft_id=row["aircraft_id"],
                req_type=row["req_type"],
                req_timestamp=row["req_timestamp"],
                msg_key=row["msg_key"],
            )
            for row in rows
        ]

    def _persist_request_queue(self) -> None:
        save_request_queue(
            self.conn,
            self.airport_id,
            [
                {
                    "aircraft_id": item.aircraft_id,
                    "req_type": item.req_type,
                    "req_timestamp": item.req_timestamp,
                    "msg_key": item.msg_key,
                }
                for item in self.request_queue
            ],
        )

    def _queue_index(self, aircraft_id: str) -> Optional[int]:
        return next((i for i, item in enumerate(self.request_queue) if item.aircraft_id == aircraft_id), None)

    def _shift_plane_up(self, aircraft_id: str, spots: int) -> None:
        if spots <= 0:
            return
        idx = self._queue_index(aircraft_id)
        if idx is None:
            return
        item = self.request_queue.pop(idx)
        target_idx = max(0, idx - spots)
        self.request_queue.insert(target_idx, item)

    # --- conflicts (REQ-TOW-015) ---

    def _record_new_conflicts(self, inbox: List[Dict[str, Any]]) -> Set[Tuple[str, str, str]]:
        """Give every conflict radar reported its own row (once), and alert command once per conflict.

        Returns the conflicts from each plane's current flight.
        """
        streaks, current = conflict_streaks(inbox)
        known = {(c["aircraft_id"], c["reason"], c["first_reported_at"]) for c in get_conflicts(self.conn, self.airport_id)}
        late_level: Dict[str, int] = {}  # how far being late has already moved each plane, this flight
        for aircraft_id, reason, first_ts in streaks:
            if (aircraft_id, reason, first_ts) not in current:
                continue  # from an earlier flight of this plane
            spots = self.spot_shifts[reason]
            if reason in LATE_REASONS:
                already = late_level.get(aircraft_id, 0)
                late_level[aircraft_id] = max(already, spots)
                spots = max(0, spots - already)
            if (aircraft_id, reason, first_ts) in known:
                continue
            conflict_id = open_conflict(self.conn, self.airport_id, aircraft_id, reason, first_ts, spots)
            enqueue_response(self.conn, self.airport_id, "command", {
                "type": CONFLICT, "conflict_id": conflict_id, "severity": CONFLICT_SEVERITY,
                "aircraft_id": aircraft_id, "reason": reason, "timestamp": first_ts,
            })
            self.conflict_changes.append({"conflict_id": conflict_id, "aircraft_id": aircraft_id, "reason": reason,
                                          "spots": spots, "status": PENDING})
        return current

    def _apply_conflicts(self, current: Set[Tuple[str, str, str]]) -> None:
        """Move each queued plane up for its pending conflicts, and resolve them.

        A plane that already holds a runway, or has departed, has nothing to move: resolved as it is.
        A plane that hasn't asked for a runway yet stays PENDING until it joins the queue.
        """
        for conflict in get_conflicts(self.conn, self.airport_id):
            if conflict["status"] != PENDING:
                continue
            aircraft_id = conflict["aircraft_id"]
            in_queue = self._queue_index(aircraft_id) is not None
            holds_runway = get_assigned_runway(self.conn, self.airport_id, aircraft_id) is not None
            left = (aircraft_id, conflict["reason"], conflict["first_reported_at"]) not in current
            if not (in_queue or holds_runway or left):
                continue
            self._shift_plane_up(aircraft_id, conflict["spots"] if in_queue else 0)
            if not resolve_conflict(self.conn, self.airport_id, conflict["conflict_id"]):
                continue
            position = self._queue_index(aircraft_id)
            resolved = {"type": CONFLICT_RESOLVED, "conflict_id": conflict["conflict_id"],
                        "aircraft_id": aircraft_id, "reason": conflict["reason"],
                        "queue_position": None if position is None else position + 1, "timestamp": now()}
            enqueue_response(self.conn, self.airport_id, "radar", resolved)
            enqueue_response(self.conn, self.airport_id, "command", {**resolved, "severity": CONFLICT_SEVERITY})
            self.conflict_changes.append({**resolved, "spots": conflict["spots"] if in_queue else 0,
                                          "status": RESOLVED})

    # --- runway requests ---

    def _enqueue_new_requests(self, inbox: List[Dict[str, Any]]) -> None:
        """New runway requests join the back of the queue, oldest request first."""
        queued_ids = {item.aircraft_id for item in self.request_queue}
        new: List[QueuedRequest] = []

        for aircraft_id, request in newest_per_plane(inbox).items():
            req_type = request["type"]
            if req_type not in (REQUEST_LANDING, REQUEST_TAKEOFF):
                continue
            req_timestamp = request.get("timestamp")
            msg_key = f"{aircraft_id}:{req_type}:{req_timestamp}"
            if is_processed(self.conn, msg_key) or aircraft_id in queued_ids:
                continue
            new.append(QueuedRequest(aircraft_id, req_type, req_timestamp, msg_key))

        # First come, first served: oldest request first; the same timestamp keeps the order radar sent them.
        new.sort(key=lambda item: item.req_timestamp or "")
        self.request_queue.extend(new)

    def _new_lifecycle_events(self, inbox: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
        """Every LANDED / PARKED / DEPARTED that came after the last message tower handled for that plane.

        "Newest message wins" is for requests (an old request shouldn't be answered). These are facts, so each new one
        is applied, in the order radar sent them: LANDED then REQUEST_TAKEOFF in one cycle must land the plane first.
        Anything before the last handled message is history and is left alone.
        """
        per_plane: Dict[str, List[Dict[str, Any]]] = {}
        for message in inbox:
            request = read_request(message)
            if request is not None:
                per_plane.setdefault(request["aircraft_id"], []).append(request)

        events: List[Tuple[str, Dict[str, Any]]] = []
        for aircraft_id, requests in per_plane.items():
            keys = [f"{aircraft_id}:{r['type']}:{r.get('timestamp')}" for r in requests]
            handled = [i for i, key in enumerate(keys) if is_processed(self.conn, key)]
            start = handled[-1] + 1 if handled else 0
            events.extend((keys[i], requests[i]) for i in range(start, len(requests))
                          if requests[i]["type"] in (LANDED, DEPARTED, PARKED))
        return events

    def _process_immediate_lifecycle_events(self, inbox: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        replies: List[Dict[str, Any]] = []

        for msg_key, request in self._new_lifecycle_events(inbox):
            aircraft_id, req_type = request["aircraft_id"], request["type"]
            if is_processed(self.conn, msg_key):
                continue

            self.request_queue = [q for q in self.request_queue if q.aircraft_id != aircraft_id]
            remove_queued_request(self.conn, self.airport_id, aircraft_id)

            if req_type == LANDED:
                set_assignment_status(self.conn, self.airport_id, aircraft_id, LANDED_PHASE)
            else:
                # Command hears about this through AIRCRAFT_PARKED / AIRCRAFT_REMOVED and RUNWAY_STATUS,
                # so FREED is only reported here (for the terminal), not sent.
                freed_runway = free_runway(self.conn, self.airport_id, aircraft_id)
                if freed_runway is not None:
                    reply = {"type": FREED, "aircraft_id": aircraft_id, "runway_id": freed_runway}
                    if req_type == PARKED:
                        reply["reason"] = PARKED
                    replies.append(reply)

            mark_processed(self.conn, msg_key)

        return replies

    def _drain_request_queue(self, busy_aircraft: Set[str]) -> List[Dict[str, Any]]:
        replies: List[Dict[str, Any]] = []
        remaining: List[QueuedRequest] = []

        for item in self.request_queue:
            aircraft_id = item.aircraft_id

            if is_processed(self.conn, item.msg_key):
                continue

            if aircraft_id in busy_aircraft and get_assigned_runway(self.conn, self.airport_id, aircraft_id) is None:
                remaining.append(item)  # being moved for separation; it gets a runway once that's done
                continue

            target_phase = TAKEOFF_ASSIGNED if item.req_type == REQUEST_TAKEOFF else LANDING_ASSIGNED
            try:
                assigned_runway = assign_runway(self.conn, self.airport_id, aircraft_id, target_phase)
            except InvalidRunwayTransition as refused:
                # e.g. REQUEST_TAKEOFF before LANDED: refuse it (radar only), take it out of the queue, and keep going.
                reply = refusal_reply(refused, item.req_type, item.req_timestamp)
                enqueue_response(self.conn, self.airport_id, "radar", reply)
                replies.append(reply)
                mark_processed(self.conn, item.msg_key)
                continue

            if assigned_runway is None:
                remaining.append(item)
                replies.extend(self._tell_waiting_once(item))
                continue

            reply = {
                "type": RUNWAY_ASSIGNED,
                "aircraft_id": aircraft_id,
                "runway_id": assigned_runway,
                "request": item.req_type,
                "request_timestamp": item.req_timestamp,
            }
            enqueue_response(self.conn, self.airport_id, "radar", reply)
            replies.append(reply)
            mark_processed(self.conn, item.msg_key)

        self.request_queue = remaining
        self._persist_request_queue()
        return replies

    def _tell_waiting_once(self, item: QueuedRequest) -> List[Dict[str, Any]]:
        """No runway free: tell radar and command NO_RUNWAY (same message as REQ-TOW-008/012), once per request."""
        told_key = f"{item.msg_key}:{NO_RUNWAY}"
        if is_processed(self.conn, told_key):
            return []
        reply = {"type": NO_RUNWAY, "aircraft_id": item.aircraft_id,
                 "request": item.req_type, "request_timestamp": item.req_timestamp}
        enqueue_response(self.conn, self.airport_id, "radar", reply)
        enqueue_response(self.conn, self.airport_id, "command", reply)
        mark_processed(self.conn, told_key)
        return [reply]

    def _flush_response_queue(self) -> List[Dict[str, Any]]:
        dispatched: List[Dict[str, Any]] = []

        for entry in get_response_queue(self.conn, self.airport_id):
            target = entry["target"]
            payload = entry["payload"]
            encoded = json.dumps(payload)

            if target == "radar":
                self.to_radar(encoded)
                remove_queued_response(self.conn, self.airport_id, entry["response_id"])
                dispatched.append(payload)
            elif target == "command":
                self.to_command(encoded)
                remove_queued_response(self.conn, self.airport_id, entry["response_id"])
                dispatched.append(payload)

        return dispatched

    def run_cycle(self) -> CycleSummary:
        inbox = self.get_inbox()
        self._load_request_queue()
        self.conflict_changes = []

        sep_pass = SeparationPass(
            self.conn,
            self.airport_id,
            inbox,
            self.to_radar,
            self.to_command,
        )
        sep_pass.close_resolved()
        sep_pass.cancel_if_a_plane_left_the_air()
        sep_pass.place_planes()
        sep_pass.retry_waiting()
        sep_pass.flag_new_pairs()

        busy_aircraft = set(sep_pass.busy)

        lifecycle_replies = self._process_immediate_lifecycle_events(inbox)
        self._enqueue_new_requests(inbox)
        current_conflicts = self._record_new_conflicts(inbox)
        self._apply_conflicts(current_conflicts)
        self._persist_request_queue()
        assigned_replies = self._drain_request_queue(busy_aircraft)
        self._flush_response_queue()

        forwarded = forward_positions(
            self.conn,
            self.airport_id,
            get=lambda: inbox,
            send=self.to_command,
        )

        remaining_responses = [entry["payload"] for entry in get_response_queue(self.conn, self.airport_id)]

        return CycleSummary(
            separation_changes=sep_pass.changed,
            request_replies=lifecycle_replies + assigned_replies,
            forwarded_messages=forwarded,
            busy_aircraft=busy_aircraft,
            queued_requests=[q.aircraft_id for q in self.request_queue],
            queued_responses=remaining_responses,
            conflict_changes=list(self.conflict_changes),
        )
