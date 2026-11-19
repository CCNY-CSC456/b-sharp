import math
import unittest

# --- Black-box unit functions being tested ---

def calculate_bounds(perimeter: float, center_lat: float, center_lon: float) -> dict:
    """Derives bounding box limits from perimeter and center."""
    d = perimeter / 8.0
    delta_lat = d / 111195.0
    # Guard against division issues near extreme poles
    cos_lat = max(0.01, math.cos(math.radians(center_lat)))
    delta_lon = d / (111195.0 * cos_lat)
    return {
        "lat_min": center_lat - delta_lat,
        "lat_max": center_lat + delta_lat,
        "lon_min": center_lon - delta_lon,
        "lon_max": center_lon + delta_lon,
    }

def project_vector_outward(center_lat: float, center_lon: float, target_lat: float, target_lon: float, distance_delta_m: float) -> tuple[float, float]:
    """Projects a point further outward along the vector originating from the center."""
    lat_diff = target_lat - center_lat
    lon_diff = target_lon - center_lon
    magnitude = math.sqrt(lat_diff**2 + lon_diff**2)

    match magnitude:
        case 0.0:
            return center_lat, center_lon
        case _:
            deg_per_meter = 1.0 / 111195.0
            scale = (magnitude + (distance_delta_m * deg_per_meter)) / magnitude
            return center_lat + (lat_diff * scale), center_lon + (lon_diff * scale)

# def calculate_bounds(perimeter: float, center_lat: float, center_lon: float) -> dict:
#   pass
#
# def project_vector_outward(center_lat: float, center_lon: float, target_lat: float, target_lon: float, distance_delta_m: float) -> tuple[float, float]:
#   pass

# --- Property / Range-Based Invariant Tests ---

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
        center_lat, center_lon = 37.7749, -122.4194  # Example origin (e.g., Airport Center)
        target_lat, target_lon = 37.8000, -122.4000  # Example aircraft position

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