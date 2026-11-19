"""REQ-OPS-007: read Tower alert events without changing shared messages.

A small replayable projection keeps old unresolved incidents even after the inbox's
latest-100 window moves on. Display policy belongs to Command; Tower owns resolution.
"""
from contextlib import closing
import json
import math
import os
from pathlib import Path
import sqlite3

from src.tower.messaging import db

TYPES = {
    'UNSAFE_SEPARATION': ('separation', 1, False),
    'UNSAFE_SEPARATION_RESOLVED': ('separation', 1, True),
    'CONFLICT': ('conflict', 2, False),
    'CONFLICT_RESOLVED': ('conflict', 2, True),
}


def identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value) if str(value).strip() else None


def text_field(event, name):
    value = event.get(name)
    return value if isinstance(value, str) else ''


def destination(event):
    lat, lon = event.get('move_to_latitude'), event.get('move_to_longitude')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lat, lon)):
        return None
    return [lat, lon] if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def project_alerts(rows):
    """Rows are (message_id, JSON content) in arrival order. Same ID updates one incident.

    Conflicts use conflict_id; separations use separation_id. The producer must
    use a new ID for a new incident. Never guess which incident a resolution clears.
    """
    incidents = {}
    opened_count = 0
    latest_message_id = 0
    ignored = 0
    for message_id, content in rows:
        latest_message_id = message_id
        try:
            event = json.loads(content)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get('type')
        if not isinstance(kind, str) or kind not in TYPES:
            continue
        family, severity, resolved = TYPES[kind]
        aircraft_id = identifier(event.get('aircraft_id'))
        incident_id = identifier(event.get('separation_id' if family == 'separation' else 'conflict_id'))
        reason = text_field(event, 'reason')
        if not aircraft_id or incident_id is None:
            ignored += 1
            continue
        key = family + ':' + incident_id
        previous = incidents.get(key)
        if resolved:
            if previous and previous['status'] != 'resolved' and aircraft_id in previous['aircraft_ids']:
                previous.update(status='resolved', updated_at=text_field(event, 'timestamp'), last_message_id=message_id)
            continue
        if previous and previous['status'] == 'resolved':
            continue  # late repeat of a completed incident; a recurrence needs a new ID
        other = identifier(event.get('other_aircraft_id'))
        aircraft_ids = list(dict.fromkeys(p for p in [aircraft_id, other] if p))
        target = destination(event) if family == 'separation' else None
        status = ('instructed' if target else 'waiting') if family == 'separation' else 'active'
        if previous is None:
            opened_count += 1
            previous = dict(key=key, opened_message_id=message_id)
            incidents[key] = previous
        previous.update(type=family, severity=severity, aircraft_ids=aircraft_ids,
                        aircraft_id=aircraft_id, reason=reason, status=status,
                        updated_at=text_field(event, 'timestamp'), last_message_id=message_id)
    values = list(incidents.values())
    active = sorted((a for a in values if a['status'] != 'resolved'), key=lambda a: (a['severity'], a['opened_message_id']))
    recent = sorted((a for a in values if a['status'] == 'resolved'), key=lambda a: a['last_message_id'], reverse=True)[:20]
    return dict(active=active, recent=recent, opened_count=opened_count,
                latest_message_id=latest_message_id, ignored_alert_count=ignored)


def get_alert_snapshot():
    path = Path(db.DB).expanduser().resolve()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as conn:
        rows = conn.execute("SELECT rowid, content FROM messages WHERE sender = 'tower' "
                            "AND recipient IN ('command', 'command-READ') ORDER BY rowid")
        snapshot = project_alerts(rows)
    try:
        sound_every = int(os.environ.get('COMMAND_ALERT_SOUND_EVERY', '10'))
        if not 1 <= sound_every <= 1000:
            raise ValueError
    except ValueError:
        sound_every = 10
    snapshot['sound_every'] = sound_every
    return snapshot
