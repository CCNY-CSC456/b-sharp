from __future__ import annotations

from dataclasses import dataclass, field
import json
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Set

from src.tower.airport.airport_repo import (
    assign_runway,
    enqueue_response,
    free_runway,
    get_assigned_runway,
    get_request_queue,
    get_response_queue,
    is_processed,
    mark_processed,
    remove_queued_request,
    remove_queued_response,
    save_request_queue,
    set_assignment_status,
)
from src.tower.airport.runway_requests import (
    DEPARTED,
    FREED,
    LANDED,
    LANDED_PHASE,
    LANDING_ASSIGNED,
    PARKED,
    REQUEST_LANDING,
    REQUEST_TAKEOFF,
    RUNWAY_ASSIGNED,
    TAKEOFF_ASSIGNED,
    forward_positions,
    newest_per_plane,
    read_json,
    read_tower_inbox,
    send_to_command,
    send_to_radar,
)
from src.tower.airport.separation import SeparationPass

PRIORITY_HIGH = "PRIORITY_HIGH"
PRIORITY_MEDIUM = "PRIORITY_MEDIUM"
PRIORITY_LOW = "PRIORITY_LOW"

PRIORITY_SPOT_SHIFTS: Dict[str, int] = {
    PRIORITY_HIGH: 3,
    PRIORITY_MEDIUM: 2,
    PRIORITY_LOW: 1,
}


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


class TowerScheduler:
    """Coordinates separation, priority spot-shifting, and SQLite-persisted queues."""

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
        self.spot_shifts = spot_shifts or dict(PRIORITY_SPOT_SHIFTS)
        self.request_queue: List[QueuedRequest] = []

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

    def _shift_plane_up(self, aircraft_id: str, spots: int) -> None:
        if spots <= 0:
            return
        idx = next((i for i, item in enumerate(self.request_queue) if item.aircraft_id == aircraft_id), None)
        if idx is None:
            return
        item = self.request_queue.pop(idx)
        target_idx = max(0, idx - spots)
        self.request_queue.insert(target_idx, item)

    def _ingest_priority_events(self, inbox: List[Dict[str, Any]]) -> Dict[str, int]:
        deferred_boosts: Dict[str, int] = {}

        for message in inbox:
            if message.get("sender") != "radar":
                continue
            data = read_json(message)
            if not isinstance(data, dict):
                continue

            event_type = data.get("type")
            if event_type not in self.spot_shifts:
                continue

            aircraft_id = data.get("aircraft_id")
            if not isinstance(aircraft_id, str):
                continue

            ts = data.get("timestamp")
            event_key = f"prio:{aircraft_id}:{event_type}:{ts}"
            if is_processed(self.conn, event_key):
                continue

            raw_spots = data.get("spots")
            spots = (
                raw_spots
                if isinstance(raw_spots, int) and not isinstance(raw_spots, bool)
                else self.spot_shifts[event_type]
            )

            idx = next((i for i, item in enumerate(self.request_queue) if item.aircraft_id == aircraft_id), None)
            if idx is not None:
                self._shift_plane_up(aircraft_id, spots)
            else:
                deferred_boosts[aircraft_id] = deferred_boosts.get(aircraft_id, 0) + spots

            mark_processed(self.conn, event_key)

        return deferred_boosts

    def _enqueue_new_requests(
        self,
        inbox: List[Dict[str, Any]],
        deferred_boosts: Dict[str, int],
    ) -> None:
        queued_ids = {item.aircraft_id for item in self.request_queue}

        for aircraft_id, request in newest_per_plane(inbox).items():
            req_type = request["type"]
            if req_type not in (REQUEST_LANDING, REQUEST_TAKEOFF):
                continue
            req_timestamp = request.get("timestamp")
            msg_key = f"{aircraft_id}:{req_type}:{req_timestamp}"
            if is_processed(self.conn, msg_key) or aircraft_id in queued_ids:
                continue

            self.request_queue.append(
                QueuedRequest(
                    aircraft_id=aircraft_id,
                    req_type=req_type,
                    req_timestamp=req_timestamp,
                    msg_key=msg_key,
                )
            )
            queued_ids.add(aircraft_id)

        for aircraft_id, spots in deferred_boosts.items():
            self._shift_plane_up(aircraft_id, spots)

    def _process_immediate_lifecycle_events(self, inbox: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        replies: List[Dict[str, Any]] = []

        for aircraft_id, request in newest_per_plane(inbox).items():
            req_type = request["type"]
            req_timestamp = request.get("timestamp")
            msg_key = f"{aircraft_id}:{req_type}:{req_timestamp}"

            if req_type not in (LANDED, DEPARTED, PARKED) or is_processed(self.conn, msg_key):
                continue

            self.request_queue = [q for q in self.request_queue if q.aircraft_id != aircraft_id]
            remove_queued_request(self.conn, self.airport_id, aircraft_id)

            if req_type == LANDED:
                set_assignment_status(self.conn, self.airport_id, aircraft_id, LANDED_PHASE)
            elif req_type == DEPARTED:
                freed_runway = free_runway(self.conn, self.airport_id, aircraft_id)
                if freed_runway is not None:
                    reply = {
                        "type": FREED,
                        "aircraft_id": aircraft_id,
                        "runway_id": freed_runway,
                    }
                    enqueue_response(self.conn, self.airport_id, "command", reply)
                    replies.append(reply)
            elif req_type == PARKED:
                freed_runway = free_runway(self.conn, self.airport_id, aircraft_id)
                if freed_runway is not None:
                    reply = {
                        "type": FREED,
                        "aircraft_id": aircraft_id,
                        "runway_id": freed_runway,
                        "reason": PARKED,
                    }
                    enqueue_response(self.conn, self.airport_id, "command", reply)
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
                remaining.append(item)
                continue

            target_phase = TAKEOFF_ASSIGNED if item.req_type == REQUEST_TAKEOFF else LANDING_ASSIGNED
            assigned_runway = assign_runway(self.conn, self.airport_id, aircraft_id, target_phase)

            if assigned_runway is None:
                remaining.append(item)
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
        deferred_boosts = self._ingest_priority_events(inbox)
        self._enqueue_new_requests(inbox, deferred_boosts)
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
        )