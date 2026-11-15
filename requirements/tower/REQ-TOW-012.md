# REQ-TOW-012

The tower subsystem shall tell command what is on each runway, and when an airplane could not get one, so command
does not have to read tower's database.

- Tower shall send command a RUNWAY_STATUS message with the runway's ID, the airplane on it (or none), its
  phase (LANDING_ASSIGNED, LANDED, TAKEOFF_ASSIGNED, or none when the runway is free), and a timestamp.
- The first time tower runs, it shall send a RUNWAY_STATUS for every runway.
- After that, tower shall send a RUNWAY_STATUS only for a runway whose airplane or phase changed since it last
  told command. A runway that did not change shall not be sent again.
- RUNWAY_STATUS shall only be sent after tower has assigned or freed the runway (REQ-TOW-007, REQ-TOW-010,
  REQ-TOW-011), so command never hears about a change before it happened.
- RUNWAY_STATUS shall go only to command. Radar keeps getting its own replies (REQ-TOW-008).
- When tower answers a request with NO_RUNWAY, it shall also send command that same NO_RUNWAY message, once,
  so command can show the airplane is waiting. Command knows the wait is over when a RUNWAY_STATUS shows
  that airplane on a runway.
