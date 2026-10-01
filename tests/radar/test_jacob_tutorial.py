# REQ-RAD-011
from src.radar.jacob_tutorial import radar_status


def test_radar_status():
    assert radar_status() == "Radar online"
