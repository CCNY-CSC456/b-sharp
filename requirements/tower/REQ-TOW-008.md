# REQ-TOW-008

The tower subsystem shall answer radar's runway requests.

- Tower shall read radar's requests for a runway to land (REQUEST_LANDING) and to take off (REQUEST_TAKEOFF) from tower's inbox.
- For each request, tower shall assign a runway if one is available (REQ-TOW-007).
- Tower shall reply to radar with RUNWAY_ASSIGNED and the runway ID, or NO_RUNWAY if none is available.
- Replies shall be JSON in the format radar reads (REQ-RAD-013).
- Messages that are not runway requests shall be ignored.
- Tower shall not send radar the same answer for the same airplane twice.
