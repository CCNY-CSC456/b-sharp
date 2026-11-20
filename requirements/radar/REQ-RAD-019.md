# REQ-RAD-019

The radar subsystem shall wait 30 seconds after a runway assignment before the runway is made available again.

- When tower sends RUNWAY_ASSIGNED (REQ-TOW-011), radar shall save the runway and start a 30 second wait
  (RUNWAY_DELAY_SECONDS, a variable so it can be changed).
- When the 30 seconds are up:
  - an airplane that asked to land shall send tower LANDED, then PARKED (tower frees the runway on PARKED),
    and radar shall set it to Parked, altitude 0, no runway, and send tower its new data (AIRCRAFT_INFO);
  - an airplane that asked to take off shall send tower DEPARTED, and radar shall clear its runway.
- Each RUNWAY_ASSIGNED shall start one wait. It is named by the request it answers, so the same runway
  assigned again for a new request starts a new wait. A reply that does not say which request it answers
  (fake-tower-reply) counts as a landing for a Landing airplane and a takeoff otherwise.
- Every airplane waits on its own; waiting never blocks radar.
- Radar shall also be able to send PARKED by hand (report-parked).
