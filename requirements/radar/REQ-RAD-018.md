# REQ-RAD-018

The radar subsystem shall send tower a conflict signal every second until tower resolves it (tower: REQ-TOW-015).

- A conflict has an airplane and one of these reasons (none are emergencies). Radar sends tower's exact text:

  | Reason (radar) | Sent as            | Tower moves it up the queue |
  |----------------|--------------------|-----------------------------|
  | LATE_2H        | "Late by +2 hour"  | 1 place                     |
  | LATE_4H        | "Late by +4 hour"  | 2 places                    |
  | LOW_FUEL       | "Low on Gas"       | 3 places                    |

- Opening a conflict shall be refused for an airplane radar does not have or an unknown reason. An airplane may
  have different reasons open at once.
- Tower counts an airplane + reason as one conflict until the airplane departs. So radar shall refuse a reason
  that is already open, or already resolved, for the airplane's current flight. After the airplane departs
  (DEPARTED), the same reason may be reported again.
- While a conflict is OPEN, radar shall send tower once per second:
  `{"type": "CONFLICT", "aircraft_id": "AA123", "reason": "Low on Gas", "timestamp": "...",
  "warning": "AA123 is low on fuel (non-emergency)"}`
  The warning text means the signal is never just a yes/no flag (tower ignores the extra field).
- Tower answers once with
  `{"type": "CONFLICT_RESOLVED", "conflict_id": 3, "aircraft_id": "AA123", "reason": "Low on Gas",
  "queue_position": 1, "timestamp": "..."}`
  Radar shall then mark its OPEN conflict for that airplane and reason RESOLVED (with the time), refresh the
  airplane's timestamp, send tower the airplane's data (AIRCRAFT_INFO), and stop sending it.
- Each CONFLICT_RESOLVED shall be used once, even if it matched nothing, so an old reply still in the inbox
  cannot close a conflict opened later. Only tower can resolve a conflict.
- Every airplane's conflicts shall be sent in the same one-second pass; opening a conflict never blocks radar.
