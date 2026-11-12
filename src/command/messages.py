"""REQ-OPS-005: non-consuming Command inbox snapshots for repeated browser refreshes."""

# HACK: as noted in NOTE, shouldn't exist, moved to tower until proper refactor

# # # # from contextlib import closing
# # # # from pathlib import Path
# # # # import sqlite3
# # # #
# # # # from src.tower.messaging import db
# # # #
# # # # from src.tower.messaging.query_fetch import load_queries
# # # # QUERIES     = load_queries("queries.sql")
# # # #
# # # # # NOTE: this entirely violates the purpose of the tower messaging system
# # # #
# # # # def get_command_messages():
# # # #     """Read recent history with unread and previously read recipient names.
# # # #
# # # #     Reading directly preserves messages already consumed by Tower's terminal
# # # #     utility and lets multiple browser tabs display the same message history.
# # # #     """
# # # #     path = Path(db.DB).expanduser().resolve()
# # # #     with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as conn:
# # # #         rows = conn.execute( QUERIES.CMD_B_04, ("command", "command-READ") ).fetchall()
# # # #     return [
# # # #         {"message_id": message_id, "sender": sender, "recipient": "command", "content": content}
# # # #         for message_id, sender, content in reversed(rows)
# # # #     ]
