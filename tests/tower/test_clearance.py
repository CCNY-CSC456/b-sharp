# REQ-TOW-004

from src.tower.clearance import takeoff_clearance

def test_takeoff_clearance():
    assert takeoff_clearance("AA123", 27) == "AA123, runway 27, cleared for takeoff."
