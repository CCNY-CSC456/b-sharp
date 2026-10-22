# REQ-RAD-014

The radar subsystem shall tell tower when an airplane is done with its runway, so tower can free it.

- When an airplane has landed, radar shall send tower a LANDED message with the aircraft ID and a timestamp. The airplane is kept unchanged.
- When an airplane has departed, radar shall send tower a DEPARTED message with the aircraft ID and a timestamp. The airplane is kept unchanged.
- Radar shall refuse to send either message for an airplane it does not have.
