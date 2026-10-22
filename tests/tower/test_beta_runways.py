"""Persisted assignments and Command integration.

REQ-TOW-006, REQ-TOW-007, REQ-TOW-008, REQ-TOW-010, REQ-TOW-011.

Use Tower's actual schema and public operations, rather than the synthetic
runway fixture or a hand-written replacement for the production tables.
"""

from contextlib import closing
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.command.dashboard import app
from src.radar.airplane import aircraft_repo, create_airplane, runway_requests as radar
from src.tower.airport import airport_repo as airport
from src.tower.airport import runway_requests as tower
from src.tower.messaging import db
from src.tower.messaging import __main__ as messaging_cli


AIRPORT_ID = "DEMO-001"


@pytest.fixture
def tower_database(tmp_path, monkeypatch):
    path = tmp_path / "tower.db"
    monkeypatch.setenv("COMMAND_TOWER_DB", str(path))
    monkeypatch.setenv("COMMAND_AIRPORT_ID", AIRPORT_ID)
    monkeypatch.setattr(db, "DB", str(tmp_path / "messages.db"))
    db.init_db()
    with closing(sqlite3.connect(path)) as conn:
        assert airport.create_tables(conn)
        assert airport.create_airport(conn, AIRPORT_ID, 21000, 40.6413, -73.7781)
    return path


def send_request(request_type, aircraft_id="AA123", timestamp="2026-10-22T14:00:00"):
    content = {"type": request_type, "aircraft_id": aircraft_id, "timestamp": timestamp}
    db.save_message("radar", "tower", json.dumps(content))


@pytest.mark.parametrize("duplicate", [(1, "OTHER"), (2, "AA123")], ids=["same-runway", "same-aircraft"])
def test_assignment_uniqueness_rolls_back_without_losing_original(tower_database, duplicate):
    with closing(sqlite3.connect(tower_database)) as conn:
        assert airport.assign_runway(conn, AIRPORT_ID, "AA123") == 1
        original = conn.execute("SELECT * FROM runway_assignments").fetchall()
        with pytest.raises(sqlite3.IntegrityError), conn:
            conn.execute(
                "INSERT INTO runway_assignments VALUES (?, ?, ?, ?, ?)",
                (AIRPORT_ID, *duplicate, "LANDING_ASSIGNED", "2026-10-22T14:00:00"),
            )
        assert not conn.in_transaction
    with closing(sqlite3.connect(tower_database)) as conn:
        assert conn.execute("SELECT * FROM runway_assignments").fetchall() == original


@pytest.mark.parametrize("existing", [False, True], ids=["new-assignment", "existing-assignment"])
@pytest.mark.parametrize("invalid_status", [
    "INVALID", "", "landing_assigned",
    pytest.param(None, marks=pytest.mark.xfail(
        strict=True,
        raises=pytest.fail.Exception,
        reason="airport_repo: assignment status is nullable; SQLite CHECK permits NULL",
    )),
])
def test_invalid_status_rolls_back_and_keeps_next_runway_available(tower_database, existing, invalid_status):
    with closing(sqlite3.connect(tower_database)) as conn:
        if existing:
            airport.assign_runway(conn, AIRPORT_ID, "AA123")
        original = conn.execute("SELECT * FROM runway_assignments").fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            airport.assign_runway(conn, AIRPORT_ID, "AA123", new_status=invalid_status)
        assert not conn.in_transaction
        assert conn.execute("SELECT * FROM runway_assignments").fetchall() == original
        assert airport.assign_runway(conn, AIRPORT_ID, "OTHER") == (2 if existing else 1)


def test_assignment_and_release_survive_reopening_connections(tower_database):
    with closing(sqlite3.connect(tower_database)) as conn:
        assert airport.assign_runway(conn, AIRPORT_ID, "AA123") == 1
    with closing(sqlite3.connect(tower_database)) as conn:
        assert airport.assign_runway(conn, AIRPORT_ID, "AA123") == 1
        assert airport.assign_runway(conn, AIRPORT_ID, "OTHER") == 2
        assert airport.free_runway(conn, AIRPORT_ID, "AA123") == 1
    with closing(sqlite3.connect(tower_database)) as conn:
        assert airport.free_runway(conn, AIRPORT_ID, "AA123") is None
        assert airport.assign_runway(conn, AIRPORT_ID, "NEXT") == 1
        assert conn.execute(
            "SELECT runway_id, aircraft_id FROM runway_assignments ORDER BY runway_id"
        ).fetchall() == [(1, "NEXT"), (2, "OTHER")]


def test_repeated_status_updates_keep_one_assignment_and_original_assignment_time(tower_database, monkeypatch):
    assigned_at = "2026-10-22T14:00:00"
    monkeypatch.setattr(airport, "now", lambda: assigned_at)
    with closing(sqlite3.connect(tower_database)) as conn:
        assert airport.assign_runway(conn, AIRPORT_ID, "AA123") == 1
        monkeypatch.setattr(airport, "now", lambda: "2026-10-22T15:00:00")
        for status in ["LANDED", "LANDED", "TAKEOFF_ASSIGNED", "TAKEOFF_ASSIGNED"]:
            assert airport.assign_runway(conn, AIRPORT_ID, "AA123", new_status=status) == 1
            assert conn.execute(
                "SELECT runway_id, aircraft_id, status, assigned_at FROM runway_assignments"
            ).fetchall() == [(1, "AA123", status, assigned_at)]


def test_duplicate_delivery_is_answered_once_even_after_restart_and_cli_read(tower_database, capsys):
    send_request(tower.REQUEST_LANDING)
    send_request(tower.REQUEST_LANDING)
    messaging_cli.show_inbox("tower")
    assert "AA123" in capsys.readouterr().out
    with closing(sqlite3.connect(tower_database)) as conn:
        assert len(tower.answer_requests(conn, AIRPORT_ID)) == 1
    send_request(tower.REQUEST_LANDING)
    with closing(sqlite3.connect(tower_database)) as conn:
        assert tower.answer_requests(conn, AIRPORT_ID) == []
        assert conn.execute("SELECT COUNT(*) FROM runway_assignments").fetchone() == (1,)
        assert conn.execute("SELECT COUNT(*) FROM processed_messages").fetchone() == (1,)
    assert len(db.get_messages("radar")) == 1


def test_failed_reply_can_retry_without_assigning_a_second_runway(tower_database):
    def unavailable(_content):
        raise RuntimeError("Temporary messaging outage")

    send_request(tower.REQUEST_LANDING)
    with closing(sqlite3.connect(tower_database)) as conn:
        with pytest.raises(RuntimeError, match="Temporary messaging outage"):
            tower.answer_requests(conn, AIRPORT_ID, send=unavailable)
        assert conn.execute("SELECT COUNT(*) FROM processed_messages").fetchone() == (0,)
    with closing(sqlite3.connect(tower_database)) as conn:
        assert tower.answer_requests(conn, AIRPORT_ID)[0]["runway_id"] == 1
        assert conn.execute("SELECT COUNT(*) FROM runway_assignments").fetchone() == (1,)
    assert len(db.get_messages("radar")) == 1


def test_radar_landing_takeoff_and_departure_reach_existing_command_client(tower_database):
    with TestClient(app) as client, closing(aircraft_repo.init_db(":memory:")) as radar_conn:
        initial = client.get("/api/airport")
        assert initial.status_code == 200
        assert len(initial.json()["runways"]) == airport.RUNWAY_COUNT
        create_airplane.create_airplane(radar_conn, "AA123", 40.77, -73.87, 2000, "Landing")
        radar.request_landing(radar_conn, "AA123")
        with closing(sqlite3.connect(tower_database)) as conn:
            assert tower.answer_requests(conn, AIRPORT_ID)[0]["runway_id"] == 1
        radar.check_tower_replies(radar_conn)
        assert aircraft_repo.get_aircraft(radar_conn, "AA123").runway_id == "1"

        response = client.get("/api/airport")
        assert response.status_code == 200
        assigned = response.json()["runways"][0]
        assert (assigned["aircraft_id"], assigned["status"], assigned["assignment_status"]) == (
            "AA123", "Not Available", "LANDING_ASSIGNED"
        )
        radar.report_landed(radar_conn, "AA123")
        with closing(sqlite3.connect(tower_database)) as conn:
            assert tower.answer_requests(conn, AIRPORT_ID) == []
        radar.request_takeoff(radar_conn, "AA123")
        with closing(sqlite3.connect(tower_database)) as conn:
            takeoff = tower.answer_requests(conn, AIRPORT_ID)[0]
            assert (takeoff["request"], takeoff["runway_id"]) == (tower.REQUEST_TAKEOFF, 1)
        cleared = client.get("/api/airport").json()["runways"][0]
        assert (cleared["aircraft_id"], cleared["status"], cleared["assignment_status"]) == (
            "AA123", "Not Available", "TAKEOFF_ASSIGNED"
        )
        radar.report_departed(radar_conn, "AA123")
        with closing(sqlite3.connect(tower_database)) as conn:
            assert tower.answer_requests(conn, AIRPORT_ID) == [
                {"type": tower.FREED, "aircraft_id": "AA123", "runway_id": 1}
            ]
        departed = client.get("/api/airport").json()["runways"][0]
        assert (departed["aircraft_id"], departed["status"], departed["assignment_status"]) == (
            None, "Available", None
        )


@pytest.mark.parametrize("landing_first", [False, True], ids=["takeoff-only", "after-landing-assignment"])
def test_takeoff_clearance_persists_takeoff_phase_for_command(tower_database, landing_first):
    if landing_first:
        send_request(tower.REQUEST_LANDING)
        with closing(sqlite3.connect(tower_database)) as conn:
            assert tower.answer_requests(conn, AIRPORT_ID)[0]["runway_id"] == 1
    send_request(tower.REQUEST_TAKEOFF)
    with closing(sqlite3.connect(tower_database)) as conn:
        reply = tower.answer_requests(conn, AIRPORT_ID)[0]
        assert reply["request"] == tower.REQUEST_TAKEOFF
    with TestClient(app) as client:
        assert client.get("/api/airport").json()["runways"][0]["assignment_status"] == "TAKEOFF_ASSIGNED"


@pytest.mark.parametrize("invalid_runway_id", [-1, 0, 11, 999])
@pytest.mark.xfail(
    strict=True,
    raises=pytest.fail.Exception,
    reason="airport_repo: assignments have no foreign key to configured airport runways",
)
def test_assignment_schema_rejects_nonexistent_runway(tower_database, invalid_runway_id):
    # assign_runway chooses IDs itself; this checks the shared table's defenses
    # against a writer inserting an assignment outside the configured airport.
    with closing(sqlite3.connect(tower_database)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError), conn:
            conn.execute(
                "INSERT INTO runway_assignments VALUES (?, ?, ?, ?, ?)",
                (AIRPORT_ID, invalid_runway_id, "AA123", "LANDING_ASSIGNED", "2026-10-22T14:00:00"),
            )


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="Command derives availability only from occupancy and hides physical runway closures",
)
def test_command_preserves_physically_unavailable_unassigned_runway(tower_database):
    with closing(sqlite3.connect(tower_database)) as conn, conn:
        conn.execute("UPDATE runways SET status = 'Not Available' WHERE runway_id = 1")
        assert airport.assign_runway(conn, AIRPORT_ID, "AA123") == 2
    with TestClient(app) as client:
        assert client.get("/api/airport").json()["runways"][0]["status"] == "Not Available"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="REQ-TOW-010: free_runway deletes the assignment without updating the runway timestamp",
)
def test_free_updates_stored_runway_timestamp(tower_database, monkeypatch):
    with closing(sqlite3.connect(tower_database)) as conn, conn:
        conn.execute("UPDATE runways SET timestamp = '2026-10-22T13:00:00'")
        airport.assign_runway(conn, AIRPORT_ID, "AA123")
        monkeypatch.setattr(airport, "now", lambda: "2026-10-22T15:00:00")
        assert airport.free_runway(conn, AIRPORT_ID, "AA123") == 1
    with closing(sqlite3.connect(tower_database)) as conn:
        assert conn.execute("SELECT timestamp FROM runways WHERE runway_id = 1").fetchone() == (
            "2026-10-22T15:00:00",
        )
