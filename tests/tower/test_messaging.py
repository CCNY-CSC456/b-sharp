# REQ-TOW-002
# Automated tests for the messaging server. CI runs these with: pytest tests/tower
# TestClient lets us call the endpoints directly, no need to start uvicorn.

from fastapi.testclient import TestClient
from src.tower.messaging import db


def make_client(tmp_path):
    # Point the database at a throwaway file so tests never touch the real messages.db
    db.DB = str(tmp_path / "test.db")
    db.init_db()
    from src.tower.messaging.main import app
    return TestClient(app)


def test_send_message(tmp_path):
    client = make_client(tmp_path)
    res = client.post("/messages", json={"sender": "radar", "recipient": "tower", "content": "hello"})
    assert res.status_code == 200
    assert res.json() == {"status": "sent"}


def test_recipient_gets_message(tmp_path):
    client = make_client(tmp_path)
    client.post("/messages", json={"sender": "radar", "recipient": "tower", "content": "AA123 inbound"})
    inbox = client.get("/messages", params={"recipient": "tower"}).json()
    assert inbox == [{"sender": "radar", "recipient": "tower", "content": "AA123 inbound"}]


def test_other_subsystems_dont_see_it(tmp_path):
    client = make_client(tmp_path)
    client.post("/messages", json={"sender": "radar", "recipient": "tower", "content": "AA123 inbound"})
    assert client.get("/messages", params={"recipient": "command"}).json() == []


def test_missing_field_rejected(tmp_path):
    client = make_client(tmp_path)
    res = client.post("/messages", json={"sender": "radar", "content": "no recipient"})
    assert res.status_code == 422
