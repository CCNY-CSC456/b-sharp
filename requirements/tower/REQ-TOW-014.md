# REQ-TOW-014

The tower subsystem shall keep a first-come-first-served runway queue, so congestion doesn't build up.

- A runway request that can't be served right away shall wait in a queue saved in tower.db (runway_request_queue),
  so it survives a restart. Requests that arrive together join the queue oldest request first;
  requests with the same timestamp keep the order radar sent them.
- Each cycle, tower shall go through the queue in order and give each airplane a free runway if there is one.
  When a runway is freed (PARKED / DEPARTED), the first airplane in the queue gets it; radar doesn't have to ask again.
- An airplane that has to wait shall be told once, to radar and command, with the same message as REQ-TOW-008/012:
  `{"type": "NO_RUNWAY", "aircraft_id": "A1", "request": "REQUEST_LANDING", "request_timestamp": "..."}`
- A request that doesn't fit the airplane's phase shall be refused (REQ-TOW-011), leave the queue, and never stop
  tower from serving the others.
- An airplane that is being moved for unsafe separation (REQ-TOW-013) shall not get a new runway until the move is done.
- Every new LANDED, PARKED, and DEPARTED shall be applied, in the order radar sent them, even when a newer request
  arrives in the same cycle (e.g. LANDED then REQUEST_TAKEOFF before tower runs: the plane lands, then is cleared).
  Only requests use "newest message wins". They shall take the airplane out of the queue. FREED is not sent to command (command hears
  through AIRCRAFT_PARKED / AIRCRAFT_REMOVED and RUNWAY_STATUS).
- Replies shall be saved (runway_response_queue) before they are sent, so a crash can't lose them.
