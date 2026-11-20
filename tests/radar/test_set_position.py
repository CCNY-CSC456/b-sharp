# REQ-RAD-020
# Automated tests for changing a plane's position by hand. CI runs these with: pytest tests/radar

# these "tests" are just bad automation of the CLI and have been moved to
# test_regressive_practices for re-education

import json
from datetime import datetime

import pytest


from src.radar.airplane.aircraft_repo import (
  create_aircraft, get_aircraft, init_db, update_position
)
from src.radar.airplane.models import AircraftTelemetry
from src.tower.messaging import db as tower_db

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)

HARD_CODED_REPLACEMENT_FOR_HARDCODED_FUNCTION_AGAIN = AircraftTelemetry(
  aircraft_id="AA123",
  latitude=40.0, longitude=70.0, altitude=3000,
  status="Landing", timestamp=OLD_TIME
)


def test_update_position_rejects_off_the_globe():
    conn = init_db(":memory:")
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARDCODED_FUNCTION_AGAIN)
    with pytest.raises(ValueError, match="latitude"):
        update_position(conn, "AA123", 91, 70.0)
    with pytest.raises(ValueError, match="longitude"):
        update_position(conn, "AA123", 40.0, -180.5)
    assert get_aircraft(conn, "AA123").latitude == 40.0
