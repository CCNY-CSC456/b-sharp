import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.tower.airport import airport_repo
from src.tower.airport.runway_requests import (
    DEPARTED,
    NO_RUNWAY,
    REQUEST_LANDING,
    REQUEST_TAKEOFF,
    RUNWAY_ASSIGNED,
)
from src.tower.airport.scheduler import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    TowerScheduler,
)


BASE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS airport (
    airport_id TEXT PRIMARY KEY,
    perimeter REAL,
    latitude REAL,
    longitude REAL
);

CREATE TABLE IF NOT EXISTS runways (
    airport_id TEXT,
    runway_id INTEGER,
    status TEXT CHECK(status IN ('Available','Not Available')),
    timestamp TEXT,
    aircraft_id TEXT,
    PRIMARY KEY (airport_id, runway_id)
);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS runway_assignments (
    airport_id TEXT NOT NULL,
    runway_id INTEGER NOT NULL,
    aircraft_id TEXT NOT NULL,
    status TEXT CHECK(status IN ('LANDING_ASSIGNED', 'LANDED', 'TAKEOFF_ASSIGNED')),
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (airport_id, runway_id),
    UNIQUE (airport_id, aircraft_id)
);

CREATE TABLE IF NOT EXISTS runway_status_sent (
    airport_id TEXT NOT NULL,
    runway_id INTEGER NOT NULL,
    aircraft_id TEXT,
    phase TEXT,
    PRIMARY KEY (airport_id, runway_id)
);

CREATE TABLE IF NOT EXISTS aircraft_positions (
    airport_id TEXT NOT NULL,
    aircraft_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    altitude REAL NOT NULL,
    status TEXT,
    on_ground INTEGER NOT NULL CHECK(on_ground IN (0, 1)),
    requested_at TEXT,
    timestamp TEXT,
    PRIMARY KEY (airport_id, aircraft_id)
);

CREATE TABLE IF NOT EXISTS separations (
    separation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport_id TEXT NOT NULL,
    aircraft_id TEXT NOT NULL,
    other_aircraft_id TEXT NOT NULL,
    move_to_latitude REAL,
    move_to_longitude REAL,
    status TEXT NOT NULL CHECK(status IN ('WAITING', 'OPEN', 'RESOLVED', 'CANCELLED')),
    opened_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS runway_request_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport_id TEXT NOT NULL,
    aircraft_id TEXT NOT NULL,
    req_type TEXT NOT NULL CHECK(req_type IN ('REQUEST_LANDING', 'REQUEST_TAKEOFF')),
    req_timestamp TEXT,
    msg_key TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (airport_id, aircraft_id)
);

CREATE TABLE IF NOT EXISTS runway_response_queue (
    response_id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport_id TEXT NOT NULL,
    target TEXT NOT NULL CHECK(target IN ('radar', 'command')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def make_test_queries():
    return SimpleNamespace(
        check_tables="SELECT name FROM sqlite_master WHERE type='table';",
        insert_airport="INSERT INTO airport VALUES (?, ?, ?, ?);",
        insert_runway="INSERT INTO runways (airport_id, runway_id, status, timestamp) VALUES (?, ?, ?, ?);",
        find_available_runway_joint="""
            SELECT r.runway_id
            FROM runways r
            LEFT JOIN runway_assignments ra
                ON r.airport_id = ra.airport_id AND r.runway_id = ra.runway_id
            WHERE r.airport_id = ?
              AND r.status = 'Available'
              AND ra.runway_id IS NULL
            ORDER BY r.runway_id
            LIMIT 1;
        """,
        insert_runway_assignment=(
            "INSERT INTO runway_assignments (airport_id, runway_id, aircraft_id, status, assigned_at) "
            "VALUES (?, ?, ?, ?, ?);"
        ),
        get_assignment="SELECT runway_id FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?;",
        get_assignment_and_status=(
            "SELECT runway_id, status FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?;"
        ),
        update_assignment_status=(
            "UPDATE runway_assignments SET status = ? WHERE airport_id = ? AND aircraft_id = ?;"
        ),
        delete_assignment="DELETE FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?;",
        mark_message_processed="INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?);",
        check_message_processed="SELECT 1 FROM processed_messages WHERE message_id = ?;",
        get_runway_status="""
            SELECT r.runway_id, ra.aircraft_id, ra.status
            FROM runways r
            LEFT JOIN runway_assignments ra
                ON r.airport_id = ra.airport_id AND r.runway_id = ra.runway_id
            WHERE r.airport_id = ?
            ORDER BY r.runway_id;
        """,
        get_sent_runway_status="SELECT runway_id, aircraft_id, phase FROM runway_status_sent WHERE airport_id = ?;",
        record_sent_runway_status=(
            "INSERT OR REPLACE INTO runway_status_sent (airport_id, runway_id, aircraft_id, phase) "
            "VALUES (?, ?, ?, ?);"
        ),
        clear_aircraft_positions="DELETE FROM aircraft_positions WHERE airport_id = ?;",
        insert_aircraft_position="""
            INSERT INTO aircraft_positions
                (airport_id, aircraft_id, latitude, longitude, altitude, status, on_ground, requested_at, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        get_aircraft_positions="""
            SELECT aircraft_id, latitude, longitude, altitude, status, on_ground, requested_at, timestamp
            FROM aircraft_positions WHERE airport_id = ? ORDER BY aircraft_id;
        """,
        get_separations="""
            SELECT separation_id, aircraft_id, other_aircraft_id, move_to_latitude, move_to_longitude,
                   status, opened_at, resolved_at
            FROM separations WHERE airport_id = ? ORDER BY separation_id;
        """,
        insert_separation="""
            INSERT INTO separations (airport_id, aircraft_id, other_aircraft_id, move_to_latitude, move_to_longitude, status, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        set_separation_move_to="""
            UPDATE separations SET move_to_latitude = ?, move_to_longitude = ?, status = 'OPEN'
            WHERE airport_id = ? AND separation_id = ? AND status = 'WAITING';
        """,
        close_separation="""
            UPDATE separations SET status = ?, resolved_at = ?
            WHERE airport_id = ? AND separation_id = ? AND status IN ('WAITING', 'OPEN');
        """,
        get_request_queue="""
            SELECT queue_id, aircraft_id, req_type, req_timestamp, msg_key, position, created_at
            FROM runway_request_queue
            WHERE airport_id = ?
            ORDER BY position ASC, queue_id ASC;
        """,
        insert_request_queue="""
            INSERT INTO runway_request_queue
                (airport_id, aircraft_id, req_type, req_timestamp, msg_key, position, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        delete_request_queue_by_aircraft=(
            "DELETE FROM runway_request_queue WHERE airport_id = ? AND aircraft_id = ?;"
        ),
        replace_request_queue="DELETE FROM runway_request_queue WHERE airport_id = ?;",
        get_response_queue="""
            SELECT response_id, target, payload_json, created_at
            FROM runway_response_queue
            WHERE airport_id = ?
            ORDER BY response_id ASC;
        """,
        insert_response_queue="""
            INSERT INTO runway_response_queue (airport_id, target, payload_json, created_at)
            VALUES (?, ?, ?, ?);
        """,
        delete_response_queue_item=(
            "DELETE FROM runway_response_queue WHERE response_id = ? AND airport_id = ?;"
        ),
    )


def radar_msg(payload: dict) -> dict:
    return {"sender": "radar", "content": json.dumps(payload)}


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    queries = make_test_queries()
    with patch.object(airport_repo, "INIT_SCHEMA", BASE_SCHEMA_SQL), patch.object(
        airport_repo, "QUERIES", queries
    ):
        assert airport_repo.create_tables(conn) is True
        assert airport_repo.create_airport(conn, "KJFK", 21000, 40.6413, -73.7781) is True
        yield conn
    conn.close()


def test_airport_repo_request_and_response_queue_persistence(db_conn):
    queries = make_test_queries()
    with patch.object(airport_repo, "QUERIES", queries):
        items = [
            {
                "aircraft_id": "AAL1",
                "req_type": REQUEST_LANDING,
                "req_timestamp": "2026-11-19T14:00:00",
                "msg_key": "AAL1:REQUEST_LANDING:2026-11-19T14:00:00",
            },
            {
                "aircraft_id": "DAL2",
                "req_type": REQUEST_TAKEOFF,
                "req_timestamp": "2026-11-19T14:00:05",
                "msg_key": "DAL2:REQUEST_TAKEOFF:2026-11-19T14:00:05",
            },
        ]
        airport_repo.save_request_queue(db_conn, "KJFK", items)
        loaded_req = airport_repo.get_request_queue(db_conn, "KJFK")
        assert [r["aircraft_id"] for r in loaded_req] == ["AAL1", "DAL2"]
        assert [r["position"] for r in loaded_req] == [0, 1]

        airport_repo.remove_queued_request(db_conn, "KJFK", "AAL1")
        remaining_req = airport_repo.get_request_queue(db_conn, "KJFK")
        assert [r["aircraft_id"] for r in remaining_req] == ["DAL2"]

        resp_id = airport_repo.enqueue_response(
            db_conn,
            "KJFK",
            "radar",
            {"type": RUNWAY_ASSIGNED, "aircraft_id": "DAL2", "runway_id": 1},
        )
        queued_resp = airport_repo.get_response_queue(db_conn, "KJFK")
        assert len(queued_resp) == 1
        assert queued_resp[0]["response_id"] == resp_id
        assert queued_resp[0]["target"] == "radar"
        assert queued_resp[0]["payload"]["aircraft_id"] == "DAL2"

        airport_repo.remove_queued_response(db_conn, "KJFK", resp_id)
        assert airport_repo.get_response_queue(db_conn, "KJFK") == []


def test_priority_events_shift_planes_by_spots_and_clamps_at_front(db_conn, monkeypatch):
    # Limit to 1 runway so queued planes wait behind a single assigned runway.
    monkeypatch.setattr("src.tower.airport.airport_repo.RUNWAY_COUNT", 1)
    queries = make_test_queries()

    with patch.object(airport_repo, "QUERIES", queries):
        # Occupy runway 1 with an existing assignment.
        # airport_repo.assign_runway(db_conn, "KJFK", "OCCUPIED", "LANDING_ASSIGNED")
        # Example: occupy all 10 runways so P1-P5 have no free runway to take
        for idx in range(1, 11):
            airport_repo.assign_runway(db_conn, "KJFK", f"BLOCKER_{idx}", "LANDING_ASSIGNED")

        # Initial queue order: P1 (0), P2 (1), P3 (2), P4 (3), P5 (4)
        initial_inbox = [
            radar_msg({"type": REQUEST_LANDING, "aircraft_id": "P1", "timestamp": "t1"}),
            radar_msg({"type": REQUEST_LANDING, "aircraft_id": "P2", "timestamp": "t1"}),
            radar_msg({"type": REQUEST_LANDING, "aircraft_id": "P3", "timestamp": "t1"}),
            radar_msg({"type": REQUEST_LANDING, "aircraft_id": "P4", "timestamp": "t1"}),
            radar_msg({"type": REQUEST_LANDING, "aircraft_id": "P5", "timestamp": "t1"}),
        ]

        radar_out = []
        cmd_out = []
        scheduler1 = TowerScheduler(
            db_conn,
            "KJFK",
            get_inbox=lambda: initial_inbox,
            to_radar=radar_out.append,
            to_command=cmd_out.append,
        )
        summary1 = scheduler1.run_cycle()
        assert summary1.queued_requests == ["P1", "P2", "P3", "P4", "P5"]
        assert radar_out == []

        # Next cycle:
        # - P4 gets PRIORITY_LOW (1 spot): index 3 -> 2  => [P1, P2, P4, P3, P5]
        # - P5 gets PRIORITY_MEDIUM (2 spots): index 4 -> 2 => [P1, P2, P5, P4, P3]
        # - P3 gets PRIORITY_HIGH (3 spots): index 4 -> 1 => [P1, P3, P2, P5, P4]
        priority_inbox = [
            radar_msg({"type": PRIORITY_LOW, "aircraft_id": "P4", "timestamp": "t2"}),
            radar_msg({"type": PRIORITY_MEDIUM, "aircraft_id": "P5", "timestamp": "t2"}),
            radar_msg({"type": PRIORITY_HIGH, "aircraft_id": "P3", "timestamp": "t2"}),
        ]

        # Simulate a restart with a brand-new TowerScheduler instance on the same DB.
        scheduler2 = TowerScheduler(
            db_conn,
            "KJFK",
            get_inbox=lambda: priority_inbox,
            to_radar=radar_out.append,
            to_command=cmd_out.append,
        )
        summary2 = scheduler2.run_cycle()
        assert summary2.queued_requests == ["P1", "P3", "P2", "P5", "P4"]

        # Clamp test: P4 (now at index 4) gets spots=99 -> clamped to index 0.
        clamp_inbox = [
            radar_msg({"type": PRIORITY_HIGH, "aircraft_id": "P4", "spots": 99, "timestamp": "t3"}),
        ]
        scheduler3 = TowerScheduler(
            db_conn,
            "KJFK",
            get_inbox=lambda: clamp_inbox,
            to_radar=radar_out.append,
            to_command=cmd_out.append,
        )
        summary3 = scheduler3.run_cycle()
        assert summary3.queued_requests == ["P4", "P1", "P3", "P2", "P5"]


def test_queued_responses_and_request_queue_survive_file_restart(tmp_path, monkeypatch):
    monkeypatch.setattr("src.tower.airport.airport_repo.RUNWAY_COUNT", 1)
    queries = make_test_queries()
    db_path = tmp_path / "tower_restart.db"

    conn1 = sqlite3.connect(db_path)
    with patch.object(airport_repo, "INIT_SCHEMA", BASE_SCHEMA_SQL), patch.object(
        airport_repo, "QUERIES", queries
    ):
        airport_repo.create_tables(conn1)
        airport_repo.create_airport(conn1, "KJFK", 21000, 40.6413, -73.7781)

        radar_sent_1 = []
        cmd_sent_1 = []
        inbox_1 = [
            radar_msg({"type": REQUEST_LANDING, "aircraft_id": "FIRST", "timestamp": "2026-11-19T14:10:00"}),
            radar_msg({"type": REQUEST_TAKEOFF, "aircraft_id": "SECOND", "timestamp": "2026-11-19T14:10:01"}),
        ]
        sched_1 = TowerScheduler(
            conn1,
            "KJFK",
            get_inbox=lambda: inbox_1,
            to_radar=radar_sent_1.append,
            to_command=cmd_sent_1.append,
        )
        res_1 = sched_1.run_cycle()

        # FIRST gets runway 1; SECOND stays queued because all runways are taken.
        assert len(radar_sent_1) == 1
        assert json.loads(radar_sent_1[0])["aircraft_id"] == "FIRST"
        assert res_1.queued_requests == ["SECOND"]
    conn1.close()

    # Reopen DB after restart: SECOND should still be queued, and freeing FIRST's runway
    # should assign runway 1 to SECOND and flush the response to radar.
    conn2 = sqlite3.connect(db_path)
    with patch.object(airport_repo, "INIT_SCHEMA", BASE_SCHEMA_SQL), patch.object(
        airport_repo, "QUERIES", queries
    ):
        radar_sent_2 = []
        cmd_sent_2 = []
        inbox_2 = [
            radar_msg({"type": DEPARTED, "aircraft_id": "FIRST", "timestamp": "2026-11-19T14:12:00"}),
        ]
        sched_2 = TowerScheduler(
            conn2,
            "KJFK",
            get_inbox=lambda: inbox_2,
            to_radar=radar_sent_2.append,
            to_command=cmd_sent_2.append,
        )
        res_2 = sched_2.run_cycle()

        assert res_2.queued_requests == []
        assigned_msgs = [
            json.loads(m) for m in radar_sent_2 if json.loads(m).get("type") == RUNWAY_ASSIGNED
        ]
        assert len(assigned_msgs) == 1
        assert assigned_msgs[0]["aircraft_id"] == "SECOND"
        assert assigned_msgs[0]["runway_id"] == 1
    conn2.close()