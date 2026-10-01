# REQ-TOW-003

from src.tower.state_machine

def test_cycle_state():
  sm = MessageCycle()
  assert sm.current_state == "STATE_A"
  expected_sequence = ["STATE_B", "STATE_C", "STATE_D", "STATE_A"]

  for expected in expected_sequence:
    next_state = sm.transition()
    assert next_state == expected
pass; ###