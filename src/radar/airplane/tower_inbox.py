# REQ-RAD-017, REQ-RAD-018, REQ-RAD-019
# tower_inbox.py — read tower's JSON messages out of radar's inbox, in one place.
#
# Every R2 feature asks the same question: "which messages of type X did TOWER send?"
# Messages from anyone else, and anything that isn't a JSON object, are skipped here,
# so the feature files only deal with well-formed tower messages.

import json
import math


def from_tower(inbox, message_type):
    """Yield the content (a dict) of every tower message of this type, oldest first."""
    for message in inbox:
        if message.get("sender") != "tower":
            continue
        try:
            data = json.loads(message["content"])
        except (ValueError, TypeError, KeyError):
            continue
        if isinstance(data, dict) and data.get("type") == message_type:
            yield data


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def as_coordinate(value, limit):
    """A finite number within +/- limit, as a float, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or abs(value) > limit:
        return None
    return float(value)
