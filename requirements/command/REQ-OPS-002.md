# REQ-OPS-002: Command–Tower Messaging

**Owning Team:** Command
**Subsystem:** Visibility

## Requirement

The Command dashboard shall send and receive messages using Tower's existing messaging service and shared message store.

## Acceptance criteria

- The dashboard sends messages with sender `command` and recipient `tower` through `POST /messages`.
- The dashboard reads `GET /messages?recipient=command`; messages addressed to another subsystem are excluded from the Command inbox.
- Messages sent by Tower's existing functions or terminal utility are readable in Command, and Command's messages are readable in Tower.
- The page polls the airport and inbox every five seconds and refreshes the inbox after sending.
- A send failure shows a useful error and preserves the unsent text.
- A messaging database failure returns HTTP 503, and the airport dashboard remains usable.
- Reuse the existing Tower schema and functions; no separate Command message database or schema is introduced.
