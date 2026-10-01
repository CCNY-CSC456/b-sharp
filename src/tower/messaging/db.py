# REQ-TOW-005
# db.py — the ONLY file that talks to the database.
# Other files call these functions instead of writing SQL themselves.
# If we ever switch databases, only this file changes.

# sqlite3 is built into Python, so there's nothing extra to install.
import sqlite3

# The database is just this file. SQLite creates it automatically the first time.
DB = "messages.db"


def init_db():
    """Create the messages table if it doesn't exist yet. Runs once when the server starts."""
    conn = sqlite3.connect(DB)  # open (or create) the database file
    # "IF NOT EXISTS" means restarting the server won't wipe or duplicate the table.
    conn.execute("CREATE TABLE IF NOT EXISTS messages (sender TEXT, recipient TEXT, content TEXT)")
    conn.commit()  # save the change to disk
    conn.close()   # close the connection when done


def save_message(sender, recipient, content):
    """Store one message as a new row in the table. Called by send.py."""
    conn = sqlite3.connect(DB)
    # The ? marks are placeholders. SQLite fills them in safely with the values,
    # so someone can't sneak SQL commands into the message content (SQL injection).
    conn.execute("INSERT INTO messages VALUES (?, ?, ?)", (sender, recipient, content))
    conn.commit()
    conn.close()


def get_messages(recipient):
    """Return every message addressed to `recipient`. Called by inbox.py."""
    conn = sqlite3.connect(DB)
    # fetchall() gives back a list of rows, each row a tuple like
    # ("radar", "tower", "AA123 at 5000ft hdg 270")
    rows = conn.execute(
        "SELECT sender, recipient, content FROM messages WHERE recipient = ?", (recipient,)
    ).fetchall()
    conn.close()
    # Turn each tuple into a dictionary so FastAPI can send it back as readable JSON:
    # {"sender": "radar", "recipient": "tower", "content": "..."}
    return [{"sender": s, "recipient": r, "content": c} for s, r, c in rows]
