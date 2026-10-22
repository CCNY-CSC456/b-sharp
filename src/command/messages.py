"""REQ-OPS-005: non-consuming Command inbox snapshots for repeated browser refreshes."""

from contextlib import closing
from pathlib import Path
import sqlite3

from src.tower.messaging import db


def get_command_messages():
    """Read recent history with both current and message_reform recipient names.

    Reading directly preserves messages already consumed by Tower's terminal
    utility and lets multiple browser tabs display the same message history.
    """
    path = Path(db.DB).expanduser().resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as conn:
        rows = conn.execute(
            "SELECT rowid, sender, content FROM messages WHERE recipient IN (?, ?) "
            "ORDER BY rowid DESC LIMIT 100", ("command", "command-READ")
        ).fetchall()
    return [
        {"message_id": message_id, "sender": sender, "recipient": "command", "content": content}
        for message_id, sender, content in reversed(rows)
    ]
