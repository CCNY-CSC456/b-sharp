# REQ-RAD-012
# models.py — defines what an "airplane" is for radar.
# Every other radar file uses these field names, so we all have to agree on this.

from datetime import datetime
from typing import Literal

# BaseModel comes from Pydantic (installed with FastAPI).
# It checks the fields for us whenever an AircraftTelemetry is created.
from pydantic import BaseModel


class AircraftTelemetry(BaseModel):
    aircraft_id: str     # unique ID, e.g. "AA123"
    latitude: float
    longitude: float
    altitude: float      # feet
    # Literal means ONLY these 3 values are allowed.
    # Anything else raises a ValidationError (which is a kind of ValueError).
    status: Literal["Parked", "Departing", "Landing"]
    timestamp: datetime  # when this data was last updated
