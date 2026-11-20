# REQ-RAD-020

The radar subsystem shall let an operator change an airplane's position by hand.

- Given an aircraft ID, a latitude and a longitude, radar shall save the new position and refresh the timestamp.
  Altitude, status and runway are not changed.
- Radar shall then send tower the airplane's updated data (AIRCRAFT_INFO, REQ-RAD-016), so tower's separation
  check and command's map use the new position.
- Latitude must be between -90 and 90 and longitude between -180 and 180. A position off the globe, or an
  airplane radar does not have, shall change nothing and send nothing.
