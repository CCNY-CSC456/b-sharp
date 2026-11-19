# REQ-TOW-015

The tower subsystem shall move an airplane up the runway queue when radar reports a conflict, and tell radar and
command once.

- Radar sends, every second until resolved:
  `{"type": "CONFLICT", "aircraft_id": "A1", "reason": "Low on Gas", "timestamp": "..."}`
  The reason shall be exactly one of "Late by +2 hour", "Late by +4 hour", "Low on Gas". Anything else is ignored.
- The repeats are one conflict: a conflict is the airplane, the reason, and the timestamp of its first message.
  After the airplane departs, the same reason is a new conflict.
- Tower shall move the airplane up the queue: Late by +2 hour 1 place, Late by +4 hour 2 places, Low on Gas 3 places,
  stopping at the front. Being late doesn't add up ("Late by +4 hour" after "Late by +2 hour" is 2 places in total);
  Low on Gas adds to it.
- If the airplane hasn't asked for a runway yet, the conflict waits (PENDING) and is applied when it joins the queue.
  If it already holds a runway, or has departed, there is nothing to move and the conflict is resolved as it is.
- Every conflict is a row in the conflicts table, and its conflict_id is used in every message about it.
- Tower to command, once, when the conflict is first reported:
  `{"type": "CONFLICT", "conflict_id": 3, "severity": 2, "aircraft_id": "A1", "reason": "Low on Gas", "timestamp": "..."}`
- Tower to radar (so it stops sending) and to command, once, when it is resolved:
  `{"type": "CONFLICT_RESOLVED", "conflict_id": 3, "aircraft_id": "A1", "reason": "Low on Gas", "queue_position": 1,
  "timestamp": "..."}` (command's copy also has `"severity": 2`; queue_position is null if the airplane isn't queued).
