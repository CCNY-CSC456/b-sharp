# REQ-TOW-005
# db.py — the ONLY file that talks to the database.
# Other files call these functions instead of writing SQL themselves.
# If we ever switch databases, only this file changes.

# sqlite3 is built into Python, so there's nothing extra to install.
import sqlite3

from src.tower.messaging.query_fetch import load_queries, load_schema
QUERIES     = load_queries("queries.sql")

DB = "messages.db"

# these are for a yet implemented refactor
BLOB = 0
JSON = 1
DATA = 2 # of a kind with (???)

# Columns added after the first version of the messages table. A messages.db made before them doesn't
# have them ("CREATE TABLE IF NOT EXISTS" never changes an existing table), so connect() adds them.
ADDED_COLUMNS = {"consumed": QUERIES.add_messages_consumed, "kind": QUERIES.add_messages_kind}


def connect():
    """Open messages.db with the current table, upgrading a table made by older code."""
    conn = sqlite3.connect(DB)
    conn.execute(QUERIES.messages_schema)
    have = {row[1] for row in conn.execute(QUERIES.messages_columns)}
    for column, add in ADDED_COLUMNS.items():
        if column not in have:
            conn.execute(add)
    conn.commit()
    return conn


def init_db():
    """Create (or upgrade) the messages table. Safe to run every time."""
    connect().close()


def save_message(sender, recipient, content, kind=BLOB):
    """Store one message as a new row in the table. Called by send.py."""
    conn = connect()
    conn.execute(QUERIES.send_message, (sender, recipient, content, kind))
    conn.commit()
    conn.close()


def get_messages(recipient):
    """Return every message addressed to `recipient` (oldest first), then add 1 to each one's 'consumed' count."""
    conn = connect()
    with conn:
        rows = conn.execute(QUERIES.default_retrieve, (recipient,)).fetchall()
        conn.executemany(QUERIES.increment_consumed, [(row[0],) for row in rows])
    conn.close()
    return [{"sender": s, "recipient": r, "content": c} for _, s, r, c in rows]
