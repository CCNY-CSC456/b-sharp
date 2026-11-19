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

def init_db():
    """Create the messages table if it doesn't exist yet. Runs once when the server starts."""
    conn = sqlite3.connect(DB)  # open (or create) the database file
    # "IF NOT EXISTS" means restarting the server won't wipe or duplicate the table.
    conn.execute(QUERIES.messages_schema)
    conn.commit()  # save the change to disk
    conn.close()   # close the connection when done


def save_message(sender, recipient, content, kind=BLOB):
    """Store one message as a new row in the table. Called by send.py."""
    conn = sqlite3.connect(DB)
    conn.execute(QUERIES.send_message, (sender, recipient, content, kind))
    # maybe instead automated hook handlers go here!
    # but probably only works for parsing
    # ie, so that can just "insert a blob (sort of)" and have it make better relational reference (?) wait no
    conn.commit()
    conn.close()



def get_messages(recipient):
  """
  Return every message addressed to `recipient`, then increment each 'consumed' count by 1.
  """
  conn = sqlite3.connect(DB)
  conn.row_factory = sqlite3.Row

  with conn:
    cursor = conn.cursor() # default_retrieve for old behavior
    rows = cursor.execute(QUERIES.default_retrieve,(recipient,)).fetchall()

    if rows:
      row_ids = [r[0] for r in rows]
      placeholders = ",".join("?" * len(row_ids))
      cursor.execute(   # Bulk increment consumed instead of mutating recipient
        f"UPDATE messages SET consumed = consumed + 1 WHERE rowid IN ({placeholders})",
        row_ids
      )
  # handlers hook here dispatched off of recipient especially relays WAIT NO
  conn.close()

  return [ {"sender": s, "recipient": r, "content": c} for _, s, r, c in rows ]
# return [{"sender": s, "recipient": r, "content": c} for s, r, c, t in rows]

