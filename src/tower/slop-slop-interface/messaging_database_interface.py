"""messaging.py — Core interface definition and storage backend."""

import sqlite3
from typing import List, Protocol, TypedDict


class MessageDict(TypedDict):
    sender: str
    recipient: str
    content: str


class MessagingStore(Protocol):
    """Abstract interface for messaging operations."""

    def init_db(self) -> None:
        """Initialize the storage schema."""
        ...

    def save_message(self, sender: str, recipient: str, content: str) -> None:
        """Save a single message to storage."""
        ...

    def get_messages(self, recipient: str) -> List[MessageDict]:
        """Retrieve all messages for a specific recipient."""
        ...


class SQLiteMessagingStore:
    """Concrete storage implementation using SQLite."""

    def __init__(self, db_path: str = "messages.db"):
        self.db_path = db_path

    def init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages "
            "(sender TEXT, recipient TEXT, content TEXT)"
        )
        conn.commit()
        conn.close()

    def save_message(self, sender: str, recipient: str, content: str) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?)",
            (sender, recipient, content),
        )
        conn.commit()
        conn.close()

    def get_messages(self, recipient: str) -> List[MessageDict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT sender, recipient, content FROM messages WHERE recipient = ?",
            (recipient,),
        ).fetchall()
        conn.close()
        return [{"sender": s, "recipient": r, "content": c} for s, r, c in rows]