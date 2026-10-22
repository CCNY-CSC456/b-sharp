# REQ-TOW-011

The tower subsystem shall clear airplanes for takeoff and free the runway once they have departed.

- Tower shall act only on each airplane's most recent message, so an old request is not answered again
  after the airplane has landed or departed.
- A REQUEST_TAKEOFF shall get its own reply, even if the airplane already holds a runway from landing.
  That reply is the airplane's clearance for takeoff.
- Every reply shall say which request it answers ("request" and "request_timestamp"), so a new request
  is always answered and a repeated one is not.
- A LANDED message shall not change the runway: a landed airplane is still on its runway.
- A DEPARTED message (the airplane went from the ground to the sky through its runway) shall free
  that airplane's runway (REQ-TOW-010). Tower does not reply to it.
