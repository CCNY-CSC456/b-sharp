# REQ-TOW-002
# Automated tests for the messaging server. CI runs these with: pytest tests/tower

import pytest
from pydantic import ValidationError
from src.tower.messaging.models import Message


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
