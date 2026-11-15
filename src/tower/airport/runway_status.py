# REQ-TOW-012
# runway_status.py — tell command what is on each runway, so it never has to read tower.db.
#
# Every run, tower compares each runway now with what it last told command, and sends a
# RUNWAY_STATUS message only for runways that changed. The first run sends every runway.
# These go to command only; radar keeps getting its own RUNWAY_ASSIGNED / NO_RUNWAY replies.

import json

from src.tower.airport.airport_repo import (
    get_runway_status, get_sent_runway_status, now, record_sent_runway_status,
)
from src.tower.airport.runway_requests import send_to_command

RUNWAY_STATUS = "RUNWAY_STATUS"  # tower -> command: who is on this runway and in which phase (or free)


def send_runway_status(conn, airport_id, send=send_to_command):
    """Send command a RUNWAY_STATUS for every runway that changed since tower last told it.

    Run this after answer_requests, so runways are already assigned / freed.
    Returns what was sent, as dicts. `send` is only there so tests can swap in a fake.
    """
    told = get_sent_runway_status(conn, airport_id)
    sent = []
    for runway_id, aircraft_id, phase in get_runway_status(conn, airport_id):
        if told.get(runway_id, "never told") == (aircraft_id, phase):
            continue  # command already knows this
        out = {"type": RUNWAY_STATUS, "runway_id": runway_id, "aircraft_id": aircraft_id,
               "phase": phase, "timestamp": now()}
        send(json.dumps(out))
        record_sent_runway_status(conn, airport_id, runway_id, aircraft_id, phase)
        sent.append(out)
    return sent
