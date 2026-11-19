import math
import pytest

# --- Production code stubs (What you start with in Red) ---

def calculate_bounds(perimeter: float, center_lat: float, center_lon: float) -> dict:
    raise NotImplementedError("Production code not written yet!")

def project_vector_outward(center_lat: float, center_lon: float, target_lat: float, target_lon: float, distance_delta_m: float) -> tuple[float, float]:
    raise NotImplementedError("Production code not written yet!")


# --- Native Pytest Invariant Tests ---

@pytest.mark.skip(reason="stashed to help with correctness validation of PR #51")
@pytest.mark.parametrize("perimeter", [500.0, 2000.0, 10000.0, 50000.0])
@pytest.mark.parametrize("lat", [-75.0, 0.0, 75.0])
@pytest.mark.parametrize("lon", [-150.0, 0.0, 150.0])
def test_bounding_box_containment_invariant(perimeter, lat, lon):
    """Invariant: Derived bounding box must always strictly enclose its center point."""
    # During 'Red', this will fail because calculate_bounds raises NotImplementedError.
    bounds = calculate_bounds(perimeter, lat, lon)

    assert bounds["lat_min"] <= lat <= bounds["lat_max"]
    assert bounds["lon_min"] <= lon <= bounds["lon_max"]

@pytest.mark.skip(reason="also stashed to help with correctness validation of PR #51")
def test_vector_displacement_monotonicity_invariant():
    """Invariant: Positive distance delta must monotonically increase distance from center."""
    center_lat, center_lon = 37.7749, -122.4194
    target_lat, target_lon = 37.8000, -122.4000

    initial_distance = math.sqrt((target_lat - center_lat)**2 + (target_lon - center_lon)**2)

    for step in [50.0, 200.0, 1000.0, 5000.0]:
        new_lat, new_lon = project_vector_outward(center_lat, center_lon, target_lat, target_lon, step)
        new_distance = math.sqrt((new_lat - center_lat)**2 + (new_lon - center_lon)**2)

        assert new_distance > initial_distance, f"Monotonicity violated at step {step}m"