# REQ-RAD-017

The radar subsystem shall move an airplane when tower reports an unsafe separation, and tell tower when it is done.

- Radar shall read tower's UNSAFE_SEPARATION messages (REQ-TOW-013):
  `{"type": "UNSAFE_SEPARATION", "separation_id": 7, "aircraft_id": "B2", "other_aircraft_id": "A1",
  "move_to_latitude": 40.81, "move_to_longitude": -73.80, "timestamp": "..."}`
- Radar shall set that airplane's latitude and longitude to the move_to coordinates and refresh its timestamp.
  Its altitude is not changed.
- Radar shall then send tower
  `{"type": "UNSAFE_SEPARATION_RESOLVED", "separation_id": 7, "aircraft_id": "B2", "timestamp": "..."}`
  followed by the airplane's new data (AIRCRAFT_INFO, REQ-RAD-016).
- Each event shall be handled once, even though radar's inbox keeps every message. An event is named by its
  separation_id, aircraft_id and timestamp, so a reused separation_id (tower.db reset) is still a new event.
- Radar shall ignore messages not sent by tower, messages that are not JSON, a separation_id that is not a
  whole number, coordinates that are missing, not numbers, or off the globe, and airplanes it does not have.
