# REQ-TOW-005
# __main__.py — the easy way to use messaging from the terminal. No server needed.
# Run from the repo root:
#   python -m src.tower.messaging send     (asks who it's from, who it's for, and the message)
#   python -m src.tower.messaging inbox    (asks whose inbox, then shows the messages)
# Python runs a file named __main__.py when you use "python -m" on its folder.

import json
import sys

# The same database functions the server uses. Nothing about them changes.
from src.tower.messaging.db import init_db, save_message, get_messages

SUBSYSTEMS = ["radar", "tower", "command"]
CHOICES = ", ".join(SUBSYSTEMS)  # "radar, tower, command"


def ask_subsystem(question):
    """Keep asking until the answer is radar, tower, or command."""
    while True:
        answer = input(f"{question} ({CHOICES}): ").strip().lower()
        if answer in SUBSYSTEMS:
            return answer
        print(f"  Please type one of: {CHOICES}")


def ask_message():
    """Keep asking until the message isn't empty."""
    while True:
        content = input("Message: ").strip()
        if content:
            return content
        print("  The message can't be empty.")


def format_content(content):
    """Make a message easy to read.

    Radar sends airplanes as JSON, like {"aircraft_id": "AA123", "status": "Parked"}.
    Those are shown as one "field: value" per line. Plain text is shown as it is.
    """
    try:
        data = json.loads(content)
    except ValueError:  # not JSON, so it's just a normal text message
        return [content]
    if not isinstance(data, dict):
        return [content]
    return [f"{field}: {value}" for field, value in data.items()]


def send():
    sender = ask_subsystem("Sender")
    recipient = ask_subsystem("Recipient")
    content = ask_message()
    save_message(sender, recipient, content)
    print(f"\nSent: {sender} -> {recipient}")


def inbox():
    show_inbox(ask_subsystem("Whose inbox?"))


def show_inbox(recipient):
    """Print every message addressed to `recipient` in a readable list."""
    messages = get_messages(recipient)
    if not messages:
        print(f"\nInbox for {recipient} is empty.")
        return
    count = "1 message" if len(messages) == 1 else f"{len(messages)} messages"
    print(f"\nInbox for {recipient} ({count})")
    print("-" * 40)
    for number, message in enumerate(messages, start=1):
        print(f"{number}. From {message['sender']}")
        for line in format_content(message["content"]):
            print(f"   {line}")
        print()  # blank line between messages


def main():
    # sys.argv is what was typed after "python -m src.tower.messaging".
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("send", "inbox"):
        print("Usage: python -m src.tower.messaging send")
        print("       python -m src.tower.messaging inbox")
        return
    init_db()  # make sure the messages table exists
    try:
        if command == "send":
            send()
        else:
            inbox()
    except (KeyboardInterrupt, EOFError):  # Ctrl+C or Ctrl+D while it's asking
        print("\nCancelled.")


if __name__ == "__main__":
    main()
