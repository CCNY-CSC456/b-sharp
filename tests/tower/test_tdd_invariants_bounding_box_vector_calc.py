import math
import pytest
import unittest

# the stuff here is still basically LLM generate stubs
from src.tower.airport.coordinates import calculate_bounds, project_vector_outward


# --- Native Pytest Invariant Tests ---

#@pytest.mark.skip(reason="stashed to help with correctness validation of PR #51")
@pytest.mark.parametrize("perimeter", [500.0, 2000.0, 10000.0, 50000.0])
@pytest.mark.parametrize("lat", [-75.0, 0.0, 75.0])
@pytest.mark.parametrize("lon", [-150.0, 0.0, 150.0])
def test_bounding_box_containment_invariant(perimeter, lat, lon):
  """Invariant: Derived bounding box must always strictly enclose its center point."""
  # During 'Red', this will fail because calculate_bounds raises NotImplementedError.
  bounds = calculate_bounds(perimeter, lat, lon)

  assert bounds["lat_min"] <= lat <= bounds["lat_max"]
  assert bounds["lon_min"] <= lon <= bounds["lon_max"]

#@pytest.mark.skip(reason="also stashed to help with correctness validation of PR #51")
def test_vector_displacement_monotonicity_invariant():
  """Invariant: Positive distance delta must monotonically increase distance from center."""
  center_lat, center_lon = 37.7749, -122.4194
  target_lat, target_lon = 37.8000, -122.4000

  initial_distance = math.sqrt((target_lat - center_lat)**2 + (target_lon - center_lon)**2)

  for step in [50.0, 200.0, 1000.0, 5000.0]:
    new_lat, new_lon = project_vector_outward(center_lat, center_lon, target_lat, target_lon, step)
    new_distance = math.sqrt((new_lat - center_lat)**2 + (new_lon - center_lon)**2)

    assert new_distance > initial_distance, f"Monotonicity violated at step {step}m"


# the unittest version
class TestSpatialInvariants(unittest.TestCase):

  def test_bounding_box_containment_invariant(self):
    """Tests that across a wide range of perimeters and geographic coordinates,
    the derived bounding box always strictly encloses its own center point.
    """
    perimeters = [500.0, 2000.0, 10000.0, 50000.0]
    latitudes = [-75.0, -45.0, 0.0, 45.0, 75.0]
    longitudes = [-150.0, -75.0, 0.0, 75.0, 150.0]

    for p in perimeters:
      for lat in latitudes:
        for lon in longitudes:
          bounds = calculate_bounds(p, lat, lon)

          # Pattern matching to classify and assert boundary state
          status = self._match_containment(bounds, lat, lon)
          self.assertEqual(
            status,
            "CONTAINED",
            f"Invariant violated for perimeter={p}, lat={lat}, lon={lon}"
          )

  def test_vector_displacement_monotonicity_invariant(self):
    """Tests that applying a positive distance delta along the center-to-target
    vector always monotonically increases the distance from the center.
    """
    center_lat, center_lon = 37.7749, -122.4194 # Example origin (e.g., Airport Center)
    target_lat, target_lon = 37.8000, -122.4000 # Example aircraft position

    initial_distance = math.sqrt((target_lat - center_lat)**2 + (target_lon - center_lon)**2)

    displacement_steps = [50.0, 200.0, 1000.0, 5000.0]
    for step in displacement_steps:
      new_lat, new_lon = project_vector_outward(center_lat, center_lon, target_lat, target_lon, step)
      new_distance = math.sqrt((new_lat - center_lat)**2 + (new_lon - center_lon)**2)

      # Pattern matching for monotonicity validation
      match new_distance > initial_distance:
        case True:
          result = "MONOTONIC_OK"
        case False:
          result = "DISTANCE_SHRUNK_OR_STAGNANT"

      self.assertEqual(
        result,
        "MONOTONIC_OK",
        f"Monotonicity violated at displacement step {step}m"
      )

  def _match_containment(self, bounds: dict, lat: float, lon: float) -> str:
    """Helper using structural pattern matching to evaluate spatial containment."""
    lat_enclosed = bounds["lat_min"] <= lat <= bounds["lat_max"]
    lon_enclosed = bounds["lon_min"] <= lon <= bounds["lon_max"]

    match (lat_enclosed, lon_enclosed):
      case (True, True):
        return "CONTAINED"
      case _:
        return "BREACHED"