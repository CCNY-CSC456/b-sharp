# REQ-RAD-012
# models.py — defines what an "airplane" is for radar.
# Every other radar file uses these field names, so we all have to agree on this.

from datetime import datetime
from typing   import Literal, Optional

from enum        import StrEnum
from dataclasses import dataclass
from datetime    import datetime
from typing      import Optional

from dataclasses import asdict
import json

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
    # REQ-RAD-013: the runway tower assigned to this plane. None until tower assigns one.
    # Optional[str] = None means it can be left out, so creating a plane works as before.
    runway_id: Optional[str] = None


from enum import StrEnum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

class AircraftStatus(StrEnum):
    PARKED = "Parked"
    DEPARTING = "Departing"
    LANDING = "Landing"

@dataclass
class AircraftShim:
  aircraft_id: str
  latitude:    float
  longitude:   float
  altitude:    float
  status:      AircraftStatus
  timestamp:   datetime
  runway_id:   Optional[str] = None

  def __post_init__(self):
    # Automatically coerce a raw string to a StrEnum if someone passes it
    if isinstance(self.status, str):
      self.status = AircraftStatus(self.status)