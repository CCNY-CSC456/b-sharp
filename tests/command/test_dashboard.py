"""REQ-OPS-001 / REQ-OPS-002: dashboard and existing Tower store integration."""

import sqlite3

from fastapi.testclient import TestClient
import pytest

from src.command import dashboard
from src.tower.messaging import db
from src.tower.messaging import __main__ as tower_cli


@pytest.fixture
def client(tmp_path, monkeypatch, tower_database):
    monkeypatch.setattr(db, "DB", str(tmp_path / "messages.db"))
    with TestClient(dashboard.app) as client:
        yield client


def test_page_has_airport_and_messaging_controls(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for element in ["airport-perimeter", "airport-coordinates", "airport-runway-count", "map-runways", "runway-list", "message-form", "message-list"]:
        assert f'id="{element}"' in response.text


def test_airport_endpoint_returns_current_snapshot(client):
    response = client.get("/api/airport")
    assert response.status_code == 200
    state = response.json()
    assert state["airport_id"] == "DEMO-001"
    assert len(state["runways"]) == 10
    assert state["assignment_source"] == "legacy_runways"


def test_command_send_is_visible_to_existing_tower_inbox(client, capsys): # TODO fails from message gc
    message = {"sender": "command", "recipient": "tower", "content": "Runway availability request"}
    response = client.post("/messages", json=message)
    assert response.status_code == 200
    assert response.json() == {"status": "sent"}
    assert db.get_messages("tower") == [message]
    tower_cli.show_inbox("tower")
    assert "Runway availability request" in capsys.readouterr().out


def test_command_inbox_reads_tower_messages_without_other_recipients(client):
    db.save_message("tower", "command", "Runway 1 available")
    db.save_message("radar", "tower", "Aircraft telemetry")
    response = client.get("/messages", params={"recipient": "command"})
    assert response.status_code == 200
    assert response.json() == [{"sender": "tower", "recipient": "command", "content": "Runway 1 available"}]


def test_invalid_message_is_not_stored(client):
    response = client.post("/messages", json={"sender": "command", "content": "Missing recipient"})
    assert response.status_code == 422
    assert db.get_messages("tower") == []


def test_empty_inbox(client):
    assert client.get("/messages", params={"recipient": "command"}).json() == []


def test_messaging_outage_does_not_prevent_airport_visibility(tmp_path, monkeypatch, tower_database):
    # A nonexistent parent makes startup and subsequent SQLite calls fail.
    monkeypatch.setattr(db, "DB", str(tmp_path / "missing" / "messages.db"))
    with TestClient(dashboard.app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/airport").status_code == 200
        assert client.get("/messages", params={"recipient": "command"}).status_code == 503
        assert client.get("/api/command-messages").status_code == 503
        response = client.post("/messages", json={"sender": "command", "recipient": "tower", "content": "Unsent"})
        assert response.status_code == 503
        assert "temporarily unavailable" in response.json()["detail"]


def test_airport_data_error_returns_service_unavailable(client, monkeypatch):
    def unavailable():
        raise sqlite3.OperationalError("private database details")

    monkeypatch.setattr(dashboard, "get_airport_state", unavailable)
    response = client.get("/api/airport")
    assert response.status_code == 503
    assert "private database details" not in response.text


def test_missing_tower_database_keeps_page_and_messages_usable(client, monkeypatch, tmp_path):
    missing = tmp_path / "not-created.db"
    monkeypatch.setenv("COMMAND_TOWER_DB", str(missing))
    assert client.get("/").status_code == 200
    assert client.get("/api/airport").status_code == 503
    assert client.get("/api/command-messages").json() == []
    assert not missing.exists()


def test_command_history_survives_repeated_reads_and_read_markers(client):
    db.save_message("tower", "command", "First message")
    db.save_message("tower", "command-READ", "Already read")
    db.save_message("radar", "tower", "Other subsystem")
    first = client.get("/api/command-messages").json()
    assert [m["content"] for m in first] == ["First message", "Already read"]
    assert all(m["recipient"] == "command" for m in first)
    assert client.get("/api/command-messages").json() == first
    with sqlite3.connect(db.DB) as conn:
        assert conn.execute("SELECT recipient FROM messages ORDER BY rowid").fetchall() == [
            ("command",), ("command-READ",), ("tower",)
        ]


def test_distinct_identical_messages_remain_distinct(client):
    db.save_message("tower", "command", "Same text")
    db.save_message("tower", "command", "Same text")
    messages = client.get("/api/command-messages").json()
    assert len(messages) == 2
    assert messages[0]["message_id"] != messages[1]["message_id"]


def test_command_history_is_bounded_and_ordered(client):
    for i in range(105):
        db.save_message("tower", "command", str(i))
    messages = client.get("/api/command-messages").json()
    assert len(messages) == 100
    assert [m["content"] for m in messages] == [str(i) for i in range(5, 105)]


def test_airport_endpoint_exposes_assignment_data(client, assignments_database):
    state = client.get("/api/airport").json()
    assert state["assignment_source"] == "runway_assignments"
    assert state["runways"][1]["aircraft_id"] == "AA123"
    assert state["runways"][1]["assignment_status"] == "LANDING_ASSIGNED"
