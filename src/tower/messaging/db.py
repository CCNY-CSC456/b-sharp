# REQ-TOW-005
# db.py — the ONLY file that talks to the database.
# Other files call these functions instead of writing SQL themselves.
# If we ever switch databases, only this file changes.

# sqlite3 is built into Python, so there's nothing extra to install.
import sqlite3


DB = "messages.db"


def init_db():
    """Create the messages table if it doesn't exist yet. Runs once when the server starts."""
    conn = sqlite3.connect(DB)  # open (or create) the database file
    # "IF NOT EXISTS" means restarting the server won't wipe or duplicate the table.
    conn.execute("CREATE TABLE IF NOT EXISTS messages (sender TEXT, recipient TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()  # save the change to disk
    conn.close()   # close the connection when done


def save_message(sender, recipient, content):
    """Store one message as a new row in the table. Called by send.py."""
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO messages (sender, recipient, content) VALUES (?, ?, ?)", (sender, recipient, content))
    conn.commit()
    conn.close()


def get_messages(recipient):
  """
  Return every unread message addressed to `recipient`, then mark them as read
  by appending '-READ' to their recipient field.
  """
  conn = sqlite3.connect(DB)

  # Enable dict-like row access if preferred, but keeping tuple unpacking here
  with conn:
    cursor = conn.cursor()

    rows = cursor.execute(
      "SELECT rowid, sender, recipient, content FROM messages WHERE recipient = ?",
      (recipient,)
    ).fetchall()

    # if rows: # extract rowids to perform a targeted bulk UPDATE
    #   row_ids = [r[0] for r in rows]
    #   placeholders = ",".join("?" * len(row_ids))
    #
    #   cursor.execute(
    #     f"UPDATE messages SET recipient = recipient || '-READ' WHERE rowid IN ({placeholders})",
    #     row_ids
    #   )

  conn.close()

  return [{"sender": s, "recipient": r, "content": c} for _, s, r, c in rows]
# return [{"sender": s, "recipient": r, "content": c} for s, r, c, t in rows]