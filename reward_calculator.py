"""
Reward Calculation Module
Distance-based reward calculation for delivery requests
"""

from typing import Optional

# Pre-calculated distances between area centers (in kilometers)
# All combinations in both directions for order flexibility
AREA_DISTANCES = {
    # SBIT distances
    ("SBIT", "SBIT"): 0.0,
    ("SBIT", "Pallri"): 2.03,
    ("SBIT", "Bahalgarh"): 8.02,
    ("SBIT", "Sonepat"): 11.03,
    ("SBIT", "TDI"): 9.03,
    ("SBIT", "New Delhi"): 31.5,

    # Reverse: To SBIT
    ("Pallri", "SBIT"): 2.03,
    ("Bahalgarh", "SBIT"): 8.02,
    ("Sonepat", "SBIT"): 11.03,
    ("TDI", "SBIT"): 9.03,
    ("New Delhi", "SBIT"): 31.5,

    # Pallri distances
    ("Pallri", "Pallri"): 0.0,
    ("Pallri", "Bahalgarh"): 7.27,
    ("Pallri", "Sonepat"): 11.36,
    ("Pallri", "TDI"): 7.14,
    ("Pallri", "New Delhi"): 30.0,

    # Reverse: To Pallri
    ("Bahalgarh", "Pallri"): 7.27,
    ("Sonepat", "Pallri"): 11.36,
    ("TDI", "Pallri"): 7.14,
    ("New Delhi", "Pallri"): 30.0,

    # Bahalgarh distances
    ("Bahalgarh", "Bahalgarh"): 0.0,
    ("Bahalgarh", "Sonepat"): 6.13,
    ("Bahalgarh", "TDI"): 6.18,
    ("Bahalgarh", "New Delhi"): 36.0,

    # Reverse: To Bahalgarh
    ("Sonepat", "Bahalgarh"): 6.13,
    ("TDI", "Bahalgarh"): 6.18,
    ("New Delhi", "Bahalgarh"): 36.0,

    # Sonepat distances
    ("Sonepat", "Sonepat"): 0.0,
    ("Sonepat", "TDI"): 12.32,
    ("Sonepat", "New Delhi"): 42.0,

    # Reverse: To Sonepat
    ("TDI", "Sonepat"): 12.32,
    ("New Delhi", "Sonepat"): 42.0,

    # TDI distances
    ("TDI", "TDI"): 0.0,
    ("TDI", "New Delhi"): 30.0,

    # Reverse: To TDI
    ("New Delhi", "TDI"): 30.0,

    # New Delhi distances
    ("New Delhi", "New Delhi"): 0.0,
}


def calculate_distance_km(area1: str, area2: str) -> float:
    """
    Get pre-calculated distance between two area centers

    Args:
        area1: First area name
        area2: Second area name

    Returns:
        float: Distance in kilometers
    """
    # Same area = 0 km
    if area1 == area2:
        return 0.0

    # Direct lookup (all combinations included in both directions)
    key = (area1, area2)

    if key in AREA_DISTANCES:
        return AREA_DISTANCES[key]
    else:
        # Unknown area combination - default to medium distance
        return 5.0


def get_base_fare(distance_km: float) -> float:
    """
    Get base fare based on distance

    Args:
        distance_km: Distance in kilometers

    Returns:
        float: Base fare in rupees
    """
    if distance_km == 0:
        return 10.0  # Same area
    elif distance_km <= 3:
        return 20.0  # Short distance
    elif distance_km <= 8:
        return 30.0  # Medium distance
    elif distance_km <= 15:
        return 40.0  # Long distance
    else:
        return 50.0  # Very long distance


def calculate_reward(
        item_price: float,
        priority: bool,
        pickup_area: Optional[str],
        drop_area: Optional[str]
) -> float:
    """
    Calculate reward for a delivery request

    Args:
        item_price: Total price of items to be delivered
        priority: Whether this is a priority request
        pickup_area: Pickup area name (e.g., "SBIT", "Pallri")
        drop_area: Drop area name

    Returns:
        float: Calculated reward amount

    Formula:
        reward = base_fare + (item_price × 5%)

    Constraints:
        - reward cannot exceed item_price (unless item_price < base_fare)
        - priority multiplies final reward by 1.5×
    """
    # Calculate distance and base fare
    if not pickup_area or not drop_area:
        # Default to medium distance if areas not provided
        base_fare = 30.0
    else:
        distance = calculate_distance_km(pickup_area, drop_area)
        base_fare = get_base_fare(distance)

    # Calculate reward: base_fare + 5% of item_price
    item_component = item_price * 0.05
    reward = base_fare + item_component

    # Apply cap: reward cannot exceed item_price (unless item_price < base_fare)
    if item_price >= base_fare:
        reward = min(reward, item_price)
    # If item_price < base_fare, no cap is applied (reward stays as calculated)

    # Apply priority multiplier
    if priority:
        reward *= 1.5

    return round(reward, 2)


def get_reward_breakdown(
        item_price: float,
        priority: bool,
        pickup_area: Optional[str],
        drop_area: Optional[str]
) -> dict:
    """
    Get detailed breakdown of reward calculation

    Returns:
        dict: Breakdown showing how reward was calculated

    Useful for:
        - Transparency to users
        - Debugging
        - Display in UI
    """
    # Calculate distance and base fare
    if not pickup_area or not drop_area:
        distance = 5.0  # Default
        base_fare = 30.0
    else:
        distance = calculate_distance_km(pickup_area, drop_area)
        base_fare = get_base_fare(distance)

    # Calculate components
    item_component = item_price * 0.05
    subtotal = base_fare + item_component

    # Check if cap applies
    cap_applied = False
    if item_price >= base_fare and subtotal > item_price:
        reward_before_priority = item_price
        cap_applied = True
    else:
        reward_before_priority = subtotal

    # Apply priority
    priority_multiplier = 1.5 if priority else 1.0
    final_reward = reward_before_priority * priority_multiplier

    return {
        "distance_km": round(distance, 2),
        "base_fare": round(base_fare, 2),
        "item_component": round(item_component, 2),
        "subtotal": round(subtotal, 2),
        "cap_applied": cap_applied,
        "reward_before_priority": round(reward_before_priority, 2),
        "priority_multiplier": priority_multiplier,
        "final_reward": round(final_reward, 2),
        "formula": "base_fare(distance) + (item_price × 5%) [capped at item_price] × priority(1.5×)"
    }


# Configuration
REWARD_CONFIG = {
    "item_percentage": 0.05,  # 5% of item price
    "priority_multiplier": 1.5,  # 1.5× for priority
    "distance_tiers": {
        "same_area": {"max_km": 0, "fare": 10.0},
        "short": {"max_km": 3, "fare": 20.0},
        "medium": {"max_km": 8, "fare": 30.0},
        "long": {"max_km": 15, "fare": 40.0},
        "very_long": {"max_km": float('inf'), "fare": 50.0}
    }
}