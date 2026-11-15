# REQ-TOW-009

The tower subsystem shall forward airplane positions from radar to command.

- Tower shall read the plane data radar sends it: the message radar sends when it creates a plane, and
  AIRCRAFT_INFO updates (REQ-RAD-016), e.g. after an altitude change.
- For each new one, tower shall send command an AIRCRAFT_POSITION message with the plane's ID, latitude,
  longitude, altitude, status, and timestamp, plus the runway tower has assigned it (or none).
- When radar reports a plane DEPARTED, tower shall send command an AIRCRAFT_REMOVED message for that plane.
- When radar reports a plane PARKED, tower shall send command an AIRCRAFT_PARKED message for that plane.
- DEPARTED and PARKED shall only be passed on after tower has handled them (freed the plane's runway).
- Messages shall be forwarded in the order radar sent them, each one once. An exact repeat shall not be
  forwarded again.
- Plane data shall not be sent back to radar, and shall never stop a runway request from being answered.
