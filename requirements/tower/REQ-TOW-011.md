# REQ-TOW-011

The tower subsystem shall clear airplanes for takeoff and free the runway once they have parked or departed.

- Tower shall act only on each airplane's most recent message, so an old request is not answered again
  after the airplane has landed or departed.
- A REQUEST_TAKEOFF shall get its own reply, even if the airplane already holds a runway from landing.
  That reply is the airplane's clearance for takeoff.
- Every reply shall say which request it answers ("request" and "request_timestamp"), so a new request
  is always answered and a repeated one is not.
- A LANDED message shall not free the runway: a landed airplane is still on its runway. Tower shall record
  the runway's phase as LANDED. Tower does not reply to it.
- A runway assignment's phase shall be LANDING_ASSIGNED for a landing clearance and TAKEOFF_ASSIGNED for a
  takeoff clearance, so command can show where each airplane is.
- A phase shall only change along these steps: none -> LANDING_ASSIGNED -> LANDED -> TAKEOFF_ASSIGNED, or
  none -> TAKEOFF_ASSIGNED for an airplane that starts on the ground. Asking for the same phase again is allowed.
- A request that doesn't fit (e.g. REQUEST_TAKEOFF while still LANDING_ASSIGNED, before LANDED) shall change
  nothing and be answered, to radar only, with:
  `{"type": "REQUEST_REFUSED", "aircraft_id": "A1", "phase": "LANDING_ASSIGNED",
  "reason": "A1 is LANDING_ASSIGNED, so it can't get TAKEOFF_ASSIGNED", "request": "REQUEST_TAKEOFF",
  "request_timestamp": "..."}`
  It shall be handled once, and shall never stop tower from answering other airplanes.
- A PARKED message (the airplane left its runway and parked) shall free that airplane's runway
  (REQ-TOW-010). Tower does not reply to it. The airplane stays at the airport.
- A DEPARTED message (the airplane went from the ground to the sky through its runway) shall free
  that airplane's runway (REQ-TOW-010). Tower does not reply to it.
