"""REQ-TOW-005: repeated reads and clients sharing the real message store."""

import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from src.command.dashboard import app
from src.tower.messaging import db
from src.tower.messaging import __main__ as cli


@pytest.fixture
def message_store(tmp_path, monkeypatch):
    path = tmp_path / "messages.db"
    monkeypatch.setattr(db, "DB", str(path))
    db.init_db()
    return path


def test_database_and_cli_reads_preserve_message_and_recipient(message_store, capsys):
    message = {"sender": "command", "recipient": "tower", "content": "Runway availability request"}
    db.save_message(**message)

    assert db.get_messages("tower") == [message]
    cli.show_inbox("tower")
    assert message["content"] in capsys.readouterr().out
    assert db.get_messages("tower") == [message]
    with closing(sqlite3.connect(message_store)) as conn:
        assert conn.execute("SELECT sender, recipient, content FROM messages").fetchall() == [
            ("command", "tower", message["content"])
        ]


def test_existing_http_clients_see_new_messages_after_empty_and_nonempty_reads(message_store):
    first = {"sender": "command", "recipient": "tower", "content": "First request"}
    second = {"sender": "command", "recipient": "tower", "content": "Second request"}
    with TestClient(app) as sender, TestClient(app) as receiver:
        assert receiver.get("/messages", params={"recipient": "tower"}).json() == []
        assert sender.post("/messages", json=first).status_code == 200
        assert receiver.get("/messages", params={"recipient": "tower"}).json() == [first]
        assert sender.post("/messages", json=second).status_code == 200
        response = receiver.get("/messages", params={"recipient": "tower"})
        assert response.status_code == 200
        assert response.json() == [first, second]
        assert receiver.get("/messages", params={"recipient": "radar"}).json() == []


def test_identical_messages_are_persisted_separately_but_reads_do_not_add_copies(message_store):
    message = {"sender": "command", "recipient": "tower", "content": "Same text"}
    db.save_message(**message)
    db.save_message(**message)

    assert db.get_messages("tower") == [message, message]
    assert db.get_messages("tower") == [message, message]
    with closing(sqlite3.connect(message_store)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (2,)
