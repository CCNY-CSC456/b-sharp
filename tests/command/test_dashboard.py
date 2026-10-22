"""REQ-OPS-001 / REQ-OPS-002: dashboard and existing Tower store integration."""

import sqlite3

from fastapi.testclient import TestClient
import pytest

from src.command import dashboard
from src.tower.messaging import db
from src.tower.messaging import __main__ as tower_cli


@pytest.fixture
def client(tmp_path, monkeypatch):
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
    assert response.json() == dashboard.get_airport_state()


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


def test_messaging_outage_does_not_prevent_airport_visibility(tmp_path, monkeypatch):
    # A nonexistent parent makes startup and subsequent SQLite calls fail.
    monkeypatch.setattr(db, "DB", str(tmp_path / "missing" / "messages.db"))
    with TestClient(dashboard.app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/airport").status_code == 200
        assert client.get("/messages", params={"recipient": "command"}).status_code == 503
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
