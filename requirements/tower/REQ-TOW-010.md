# REQ-TOW-010

The tower subsystem shall free an airplane's runway so it can be assigned again.

- Freeing an airplane's runway shall set it back to "Available", clear the airplane's ID, and update its timestamp.
- Only that airplane's runway shall change.
- If the airplane has no runway, nothing shall change and tower shall report that nothing was freed.
- A freed runway shall be available to assign to another airplane (REQ-TOW-007).
