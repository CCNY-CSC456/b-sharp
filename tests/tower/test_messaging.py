# REQ-TOW-002
# Automated tests for the messaging server. CI runs these with: pytest tests/tower
# TestClient lets us call the endpoints directly, no need to start uvicorn.

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from src.tower.messaging.models import Message
from src.tower.messaging import db


# --- models.py ---

def test_valid_message():
    msg = Message(sender="radar", recipient="tower", content="AA123 at 5000ft hdg 270")
    assert msg.sender == "radar"
    assert msg.recipient == "tower"
    assert msg.content == "AA123 at 5000ft hdg 270"


def test_message_missing_field_raises():
    # No recipient, so Pydantic should refuse to build the Message.
    with pytest.raises(ValidationError):
        Message(sender="radar", content="no recipient")


# --- db.py ---

def use_temp_db(tmp_path):
    # Point the database at a throwaway file so tests never touch the real messages.db
    db.DB = str(tmp_path / "test.db")
    db.init_db()


def test_save_and_get_message(tmp_path):
    use_temp_db(tmp_path)
    db.save_message("radar", "tower", "AA123 inbound")
    assert db.get_messages("tower") == [
        {"sender": "radar", "recipient": "tower", "content": "AA123 inbound"}
    ]


def test_other_recipient_gets_nothing(tmp_path):
    use_temp_db(tmp_path)
    db.save_message("radar", "tower", "AA123 inbound")
    assert db.get_messages("command") == []


# --- endpoints (main.py + send.py + inbox.py) ---

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
