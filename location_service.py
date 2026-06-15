"""
GPS Location Service - With overlap handling and edge case management

Production-hardened:
- All Firestore I/O is async (non-blocking event loop)
- Timezone-aware timestamps throughout
"""

from typing import Dict, Optional, List, Any
from fastapi import HTTPException
import math

from firestore_async import (
    get_db, utcnow,
    get_doc, update_doc, set_doc,
    build_query, stream_query,
)

# Define GPS boundaries for each area
AREA_BOUNDARIES = {
    "SBIT": {
        "center": (28.9890834, 77.1506293),
        "radius_m": 407.93
    },
    "Pallri": {
        "center": (28.9709633, 77.1531023),
        "radius_m": 1700.0
    },
    "Bahalgarh": {
        "center": (28.9470954, 77.0835646),
        "radius_m": 3200.0
    },
    "Sonepat": {
        "center": (28.9845887, 77.0373188),
        "radius_m": 3500.0
    },
    "TDI": {
        "center": (28.9098117, 77.1307161),
        "radius_m": 2300.0
    }
}

BUFFER_ZONE_METERS = 50

# Pre-calculate optimized boundaries
AREA_BOUNDARIES_OPTIMIZED: Dict[str, Dict[str, Any]] = {}
for _area, _data in AREA_BOUNDARIES.items():
    _radius = _data["radius_m"]
    _radius_buf = _radius + BUFFER_ZONE_METERS
    AREA_BOUNDARIES_OPTIMIZED[_area] = {
        **_data,
        "radius_squared": _radius ** 2,
        "radius_with_buffer": _radius_buf,
        "radius_with_buffer_squared": _radius_buf ** 2,
    }


def quick_distance_check(
    lat1: float, lon1: float, lat2: float, lon2: float, max_distance_m: float
) -> Optional[bool]:
    """Fast bounding-box pre-check."""
    max_degrees = max_distance_m / 111000.0
    lat_diff = abs(lat1 - lat2)
    lon_diff = abs(lon1 - lon2)

    if lat_diff > max_degrees or lon_diff > max_degrees:
        return False
    if lat_diff < 0.009 and lon_diff < 0.009:
        return True
    return None


def calculate_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters."""
    R = 6371000.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def detect_area_from_coordinates_fast(latitude: float, longitude: float) -> Optional[str]:
    """Ultra-fast area detection — primary area name or None."""
    for area_name, boundary in AREA_BOUNDARIES_OPTIMIZED.items():
        center_lat, center_lon = boundary["center"]
        radius_with_buffer = boundary["radius_with_buffer"]

        quick_check = quick_distance_check(latitude, longitude, center_lat, center_lon, radius_with_buffer)
        if quick_check is False:
            continue
        if quick_check is True:
            distance = calculate_distance_meters(latitude, longitude, center_lat, center_lon)
            if distance <= boundary["radius_m"]:
                return area_name

        distance = calculate_distance_meters(latitude, longitude, center_lat, center_lon)
        if distance <= boundary["radius_m"]:
            return area_name

    # Not strictly inside any area → find nearest center
    min_distance = float("inf")
    nearest_area = None
    for area_name, boundary in AREA_BOUNDARIES_OPTIMIZED.items():
        center_lat, center_lon = boundary["center"]
        distance = calculate_distance_meters(latitude, longitude, center_lat, center_lon)
        if distance < min_distance:
            min_distance = distance
            nearest_area = area_name

    if min_distance <= 10_000:
        return f"{nearest_area}_nearby"
    return None


def detect_area_from_coordinates(
    latitude: float,
    longitude: float,
    include_nearby: bool = False,
    max_unrecognized_distance_m: float = 10000.0
) -> Dict[str, Any]:
    """Detect which predefined area(s) the GPS coordinates fall into."""
    matching_areas: List[str] = []
    distances_calculated: Dict[str, float] = {}

    for area_name, boundary in AREA_BOUNDARIES.items():
        center_lat, center_lon = boundary["center"]
        distance = calculate_distance_meters(latitude, longitude, center_lat, center_lon)
        distances_calculated[area_name] = distance
        if distance <= boundary["radius_m"]:
            matching_areas.append(area_name)

    primary_area: Optional[str]
    is_on_edge = False

    if matching_areas:
        primary_area = min(matching_areas, key=lambda a: distances_calculated[a])
        closest_distance = distances_calculated[primary_area]
        primary_radius = AREA_BOUNDARIES[primary_area]["radius_m"]
        is_on_edge = closest_distance >= (primary_radius - BUFFER_ZONE_METERS)
    else:
        closest_area_name, closest_distance = min(distances_calculated.items(), key=lambda x: x[1])
        closest_radius = AREA_BOUNDARIES[closest_area_name]["radius_m"]
        if closest_distance <= max_unrecognized_distance_m:
            if closest_distance <= (closest_radius + BUFFER_ZONE_METERS):
                primary_area = closest_area_name
                matching_areas.append(closest_area_name)
                is_on_edge = True
            else:
                primary_area = f"{closest_area_name}_nearby"
                is_on_edge = False
        else:
            primary_area = None
            is_on_edge = False

    nearby_areas: List[Dict[str, Any]] = []
    if include_nearby:
        for area_name, distance in distances_calculated.items():
            if area_name not in matching_areas:
                area_radius = AREA_BOUNDARIES[area_name]["radius_m"]
                if distance <= (area_radius + BUFFER_ZONE_METERS):
                    nearby_areas.append({
                        "area": area_name,
                        "distance_meters": round(distance, 2),
                        "distance_from_edge": round(distance - area_radius, 2),
                    })

    return_distances = {} if matching_areas else {k: round(v, 2) for k, v in distances_calculated.items()}

    return {
        "primary_area": primary_area,
        "all_matching_areas": matching_areas,
        "nearby_areas": nearby_areas,
        "is_on_edge": is_on_edge,
        "distances": return_distances,
    }


async def update_user_location(
    user_uid: str,
    latitude: float,
    longitude: float,
    accuracy: Optional[float] = None,
    fast_mode: bool = False
) -> Dict[str, Any]:
    """Update user's GPS location and auto-detect area with edge handling."""
    if not (-90 <= latitude <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
    if not (-180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")

    if fast_mode:
        primary_area = detect_area_from_coordinates_fast(latitude, longitude)
        area_info = {
            "primary_area": primary_area,
            "all_matching_areas": [primary_area] if primary_area else [],
            "is_on_edge": False,
            "nearby_areas": [],
        }
    else:
        area_info = detect_area_from_coordinates(latitude, longitude, include_nearby=True)

    now = utcnow()
    location_data: Dict[str, Any] = {
        "gps_location": {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "last_updated": now,
        },
        "current_area": area_info["primary_area"],
        "updated_at": now,
    }

    if not fast_mode:
        location_data.update({
            "all_areas": area_info["all_matching_areas"],
            "is_on_area_edge": area_info["is_on_edge"],
            "nearby_areas": area_info["nearby_areas"],
        })

    try:
        await update_doc('users', user_uid, location_data)
    except Exception:
        await set_doc('users', user_uid, location_data, merge=True)

    # Build a friendly message
    if area_info["primary_area"]:
        if isinstance(area_info["primary_area"], str) and area_info["primary_area"].endswith("_nearby"):
            base_area = area_info["primary_area"].replace("_nearby", "")
            message = f"Location updated. Near {base_area} (outside main area)"
        else:
            message = f"Location updated. You are in {area_info['primary_area']}"
            if not fast_mode and area_info["is_on_edge"]:
                message += " (near boundary)"
            if not fast_mode and len(area_info["all_matching_areas"]) > 1:
                other_areas = [a for a in area_info["all_matching_areas"] if a != area_info["primary_area"]]
                if other_areas:
                    message += f". Also overlapping with: {', '.join(other_areas)}"
    else:
        message = "Location updated. Not near any defined area"

    return {
        "latitude": latitude,
        "longitude": longitude,
        "primary_area": area_info["primary_area"],
        "all_matching_areas": area_info.get("all_matching_areas", []),
        "is_on_edge": area_info.get("is_on_edge", False),
        "nearby_areas": area_info.get("nearby_areas", []),
        "accuracy": accuracy,
        "message": message,
    }


async def get_nearby_users(
    latitude: float,
    longitude: float,
    radius_m: float = 5000.0,
    max_results: int = 50
) -> List[Dict[str, Any]]:
    """Find users within a certain radius of given coordinates."""
    q = build_query('users', filters=[('is_reachable', '==', True)])
    reachable_users = await stream_query(q)

    nearby_users: List[Dict[str, Any]] = []
    for user_data in reachable_users:
        gps_location = user_data.get("gps_location")
        if not gps_location:
            continue

        user_lat = gps_location.get("latitude")
        user_lon = gps_location.get("longitude")
        if user_lat is None or user_lon is None:
            continue

        distance = calculate_distance_meters(latitude, longitude, user_lat, user_lon)
        if distance <= radius_m:
            nearby_users.append({
                "uid": user_data.get("uid"),
                "email": user_data.get("email"),
                "name": user_data.get("name"),
                "current_area": user_data.get("current_area"),
                "all_areas": user_data.get("all_areas", []),
                "is_on_edge": user_data.get("is_on_area_edge", False),
                "distance_meters": round(distance, 2),
                "distance_km": round(distance / 1000, 2),
                "gps_accuracy": gps_location.get("accuracy"),
            })

    nearby_users.sort(key=lambda x: x["distance_meters"])
    return nearby_users[:max_results]


async def is_user_in_area(user_uid: str, area_name: str) -> Dict[str, Any]:
    """Check if user's current GPS location is within a specific area."""
    user_data = await get_doc('users', user_uid)
    if not user_data:
        return {"is_in_area": False, "reason": "User not found"}

    current_area = user_data.get("current_area")
    all_areas = user_data.get("all_areas", [])
    is_on_edge = user_data.get("is_on_area_edge", False)

    is_in_area = (current_area == area_name) or (area_name in all_areas)

    return {
        "is_in_area": is_in_area,
        "primary_area": current_area,
        "all_matching_areas": all_areas,
        "is_on_edge": is_on_edge,
        "requested_area": area_name,
    }


async def get_users_in_area(
    area_name: str,
    include_edge_users: bool = True
) -> List[Dict[str, Any]]:
    """Get all reachable users in a specific area."""
    q = build_query('users', filters=[('is_reachable', '==', True)])
    reachable_users = await stream_query(q)

    users_in_area: List[Dict[str, Any]] = []
    for user_data in reachable_users:
        current_area = user_data.get("current_area")
        all_areas = user_data.get("all_areas", [])
        is_on_edge = user_data.get("is_on_area_edge", False)

        is_match = (current_area == area_name) or (area_name in all_areas)
        if is_match and (include_edge_users or not is_on_edge):
            users_in_area.append({
                "uid": user_data.get("uid"),
                "email": user_data.get("email"),
                "name": user_data.get("name"),
                "current_area": current_area,
                "all_areas": all_areas,
                "is_on_edge": is_on_edge,
            })

    return users_in_area


async def calculate_delivery_distance(
    pickup_location: Dict[str, float],
    drop_location: Dict[str, float]
) -> Dict[str, Any]:
    """Calculate distance between pickup and drop locations and determine areas."""
    distance_m = calculate_distance_meters(
        pickup_location["latitude"], pickup_location["longitude"],
        drop_location["latitude"], drop_location["longitude"]
    )

    pickup_area_info = detect_area_from_coordinates(
        pickup_location["latitude"], pickup_location["longitude"]
    )
    drop_area_info = detect_area_from_coordinates(
        drop_location["latitude"], drop_location["longitude"]
    )

    pickup_primary = pickup_area_info.get("primary_area")
    drop_primary = drop_area_info.get("primary_area")

    return {
        "distance_meters": round(distance_m, 2),
        "distance_km": round(distance_m / 1000, 3),
        "pickup_area": pickup_primary,
        "drop_area": drop_primary,
        "crosses_areas": pickup_primary != drop_primary,
    }


def get_area_info(area_name: str) -> Optional[Dict[str, Any]]:
    """Get information about a specific area."""
    if area_name not in AREA_BOUNDARIES:
        return None
    boundary = AREA_BOUNDARIES[area_name]
    return {
        "name": area_name,
        "center": {"latitude": boundary["center"][0], "longitude": boundary["center"][1]},
        "radius_meters": boundary["radius_m"],
        "radius_km": round(boundary["radius_m"] / 1000, 3),
    }


def get_all_areas_info() -> List[Dict[str, Any]]:
    """Get information about all defined areas."""
    return [get_area_info(area_name) for area_name in AREA_BOUNDARIES.keys()]
