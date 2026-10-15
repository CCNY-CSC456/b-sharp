"""REQ-OPS-001: hard-coded airport state for Command's first R1 increment."""

from copy import deepcopy
from datetime import datetime, timezone

from src.tower.airport.airport_repo import RUNWAY_COUNT

_updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

# Tower does not specify a perimeter unit, so display its numeric value unchanged.
_AIRPORT_STATE = {
    "airport_id": "DEMO-001",
    "perimeter": 21000,
    "latitude": 40.6413,
    "longitude": -73.7781,
    "runways": [
        {
            "runway_id": runway_id,
            "status": "Not Available" if runway_id == RUNWAY_COUNT else "Available",
            "timestamp": _updated_at,
        }
        for runway_id in range(1, RUNWAY_COUNT + 1)
    ],
}


def get_airport_state():
    """Return a copy of the demo snapshot with its runway count."""
    airport = deepcopy(_AIRPORT_STATE)
    airport["number_of_runways"] = len(airport["runways"])
    return airport
