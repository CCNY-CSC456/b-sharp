# REQ-RAD-017, REQ-RAD-018, REQ-RAD-019
# monitor.py — radar's run loop. Once every second, for every plane at once:
#   1. move planes tower said are too close, and tell tower they moved   (separation.py,   REQ-RAD-017)
#   2. close conflicts tower resolved                                     (conflicts.py,    REQ-RAD-018)
#   3. save new runway assignments and start their 30 second wait         (runway_delay.py, REQ-RAD-019)
#   4. land/park or depart planes whose 30 seconds are up                 (runway_delay.py, REQ-RAD-019)
#   5. send CONFLICT for every conflict that is still open                (conflicts.py,    REQ-RAD-018)
#
# The inbox is read ONCE per tick and shared by every step, so more planes means more rows to look at,
# not more trips to the messages database. Run it with:  python -m src.radar.airplane run

import time

from src.radar.airplane.aircraft_repo import now
from src.radar.airplane.conflicts import apply_conflict_resolutions, send_open_conflicts
from src.radar.airplane.runway_delay import apply_runway_assignments, finish_due_runways
from src.radar.airplane.runway_requests import read_radar_inbox, send_to_tower
from src.radar.airplane.separation import handle_unsafe_separation

TICK_SECONDS = 1.0   # "Send a Conflict message to Tower every (1) sec until resolved"


def tick(conn, get=read_radar_inbox, send=send_to_tower, clock=now):
    """Do steps 1-5 once. Returns what happened, as text (conflict signals are counted, not listed)."""
    inbox = get()
    results = []
    results += handle_unsafe_separation(conn, inbox, send=send, clock=clock)
    results += apply_conflict_resolutions(conn, inbox, send=send, clock=clock)
    results += apply_runway_assignments(conn, inbox, clock=clock)
    results += finish_due_runways(conn, send=send, clock=clock)
    signals = send_open_conflicts(conn, send=send, clock=clock)
    if signals:
        results.append(f"sent {len(signals)} conflict signal(s): "
                       + ", ".join(f"{s['aircraft_id']} {s['reason']}" for s in signals))
    return results


def run(conn, get=read_radar_inbox, send=send_to_tower, clock=now, sleep=time.sleep, ticks=None, out=print):
    """Tick every TICK_SECONDS until Ctrl+C (or `ticks` times, for tests and `run --once`)."""
    out(f"Radar running: checking tower every {TICK_SECONDS:g}s. Press Ctrl+C to stop.")
    done = 0
    try:
        while ticks is None or done < ticks:
            for line in tick(conn, get=get, send=send, clock=clock):
                out(f"[{clock():%H:%M:%S}] {line}")
            done += 1
            sleep(TICK_SECONDS)
    except KeyboardInterrupt:
        pass
    out("Radar stopped.")
