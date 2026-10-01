
class MessageCycle:
    def __init__(self):
        self._states = ["STATE_A", "STATE_B", "STATE_C", "STATE_D"]
        self._current_index = 0

    @property
    def current_state(self) -> str:
        """Reports the system's current state."""
        return self._states[self._current_index]

    def transition(self) -> str:
        """Advances the state machine to the next state in the cycle."""
        self._current_index = (self._current_index + 1) % len(self._states)
        return self.current_state
