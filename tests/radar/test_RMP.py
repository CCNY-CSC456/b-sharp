from src.radar.RMP import readiness


def test_readiness():
    assert readiness() == "Radar: Ready"
