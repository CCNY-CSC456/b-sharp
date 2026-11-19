
import math


# --- Production code stubs (What you start with in Red) ---

# def calculate_bounds(perimeter: float, center_lat: float, center_lon: float) -> dict:
#     raise NotImplementedError("Production code not written yet!")
#
# def project_vector_outward(center_lat: float, center_lon: float, target_lat: float, target_lon: float, distance_delta_m: float) -> tuple[float, float]:
#     raise NotImplementedError("Production code not written yet!")


MAGIC_CONVERSION_CONSTANT = 111195.0

def calculate_bounds(perimeter: float, center_lat: float, center_lon: float) -> dict:
  """Derives bounding box limits from perimeter and center."""
  d = perimeter / 8.0
  delta_lat = d / MAGIC_CONVERSION_CONSTANT
  # Guard against division issues near extreme poles
  cos_lat = max(0.01, math.cos(math.radians(center_lat)))
  delta_lon = d / (MAGIC_CONVERSION_CONSTANT * cos_lat)
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
      deg_per_meter = 1.0 / MAGIC_CONVERSION_CONSTANT
      scale = (magnitude + (distance_delta_m * deg_per_meter)) / magnitude
      return center_lat + (lat_diff * scale), center_lon + (lon_diff * scale)