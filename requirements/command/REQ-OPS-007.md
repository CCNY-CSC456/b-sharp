# REQ-OPS-007: R2 Tower Alerts

**Owning Team:** Command

Command shall notify the operator of Tower's important events, rank alerts by severity, avoid alert spam, allow an operator response, and update the UI when Tower resolves an event.

## Acceptance criteria

- Receive `UNSAFE_SEPARATION`, `CONFLICT`, and their resolved messages from Tower through the existing message store.
- Show unsafe separation as severity 1 before severity-2 conflicts, with the affected aircraft and alert reason/status.
- Change aircraft colors while alerts are active, with text descriptions. The highest active severity wins; resolving one alert must preserve other active warnings. Clear all warnings for an aircraft when all its incidents are resolved.
- Repeated reports update one alert rather than adding repeated cards. Re-reading existing messages never generates new notifications.
- Play one distinctive sound per configurable number of new incidents (default 10). `COMMAND_ALERT_SOUND_EVERY` changes the value at startup; accepted integers 1–1000, invalid values fall back to 10. Counting distinct incident openings is the documented demo interpretation.
- Let operators select the affected aircraft or prepare a message using the existing Tower messaging form. Contact Tower preserves an existing draft and requires the operator to send it.
- Update the UI on a matching resolution and retain a small, collapsed list of recently cleared alerts so the operator can see what happened.
- Preserve R1 dashboard behavior and degraded-data warnings. Latency enforcement and database-access migration remain deferred for this demo.

## Implementation notes

- `/api/alerts` reads only messages from `tower` to `command` or `command-READ`, without modifying shared messages. It replays history so old unresolved alerts survive the inbox's latest-100 window.
- Separation events use Tower's `separation_id`. A null destination means waiting; a later instructed destination updates that same incident. Command never changes a map position from an instruction.
- Conflict events use `conflict_id`. Resolutions retain their incident ID and aircraft ID. New incidents require new IDs; completed IDs are not reopened by late repeat messages. Missing IDs are reported instead of guessing what to clear.
- Audio is enabled by default. A click or keypress unlocks browser audio; operators can mute it. Test Sound checks the speaker separately from the incident counter. Initial history and reloads are silent; muted sounds are not queued. At most one tone plays per refresh batch.
- The UI has no separate acknowledgement state or persistent browser storage. Tower controls resolution.

## Integration status

Unsafe separation is exercised against real Tower producers on main. The severity-2 producer is not present in the reviewed main; Tower has proposed the matching format below; its queue producer is still being implemented. Command already accepts it.

```json
{"type":"CONFLICT","conflict_id":"fuel-A1-1","severity":2,"aircraft_id":"A1","reason":"Low on gas (non-emergency)","timestamp":"2026-11-19T10:00:00"}
```

The resolved event changes `type` to `CONFLICT_RESOLVED`, retaining `conflict_id` and `aircraft_id`, with `reason`, `queue_position`, and `timestamp`. These additional fields are accepted without requiring a parser change; the full payload remains available in Tower messages. The JSON payload is a string in the existing message envelope with sender `tower`, recipient `command`.

## Verification

`tests/command/test_alerts.py` covers severity, repeat/resolution handling, full history, source filtering, API failures, configuration and real Tower events. `tests/command/browser_alerts.cjs` checks aircraft colors, sounds, simple operator actions, resolution, stale/recovery behavior and mobile layout. The full Python suite checks existing R1 behavior.
