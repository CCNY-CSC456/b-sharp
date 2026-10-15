"""REQ-OPS-001: hard-coded airport state for Command's first R1 increment."""

from copy import deepcopy
from datetime import datetime, timezone

from src.tower.airport.airport_repo import RUNWAY_COUNT

_updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

# Match Tower's field names, numeric perimeter, runway IDs, and status values.
# These are demo values, not a read from Tower's database. Tower has not specified
# a perimeter unit, so Command displays the number without inventing a unit.
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
    """Return an independent demo snapshot, deriving the count from its runways.

    This is the replaceable read boundary for a later Tower database integration.
    The demo timestamps use UTC and describe when the sample was initialized.
    """
    airport = deepcopy(_AIRPORT_STATE)
    airport["number_of_runways"] = len(airport["runways"])
    return airport
