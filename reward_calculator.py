"""
Reward Calculation Module
Centralized logic for auto-calculating delivery rewards
"""

from typing import Optional


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
        
    Note:
        This is a placeholder function. The actual reward calculation
        logic will be implemented later based on business requirements.
        
        Factors that can be considered:
        - Item price (base percentage)
        - Priority multiplier
        - Cross-area delivery bonus
        - Minimum and maximum bounds
        - Surge pricing (time of day, demand)
    """
    
    # PLACEHOLDER LOGIC - TO BE IMPLEMENTED LATER
    # For now, return a simple default based on item price
    
    base_reward = item_price * 0.10  # 10% of item price
    
    # Apply priority multiplier
    if priority:
        base_reward *= 1.5  # 50% bonus for priority
    
    # Cross-area bonus
    if pickup_area and drop_area and pickup_area != drop_area:
        base_reward += 20.0  # Flat ₹20 bonus
    
    # Ensure minimum reward
    min_reward = 20.0
    
    return max(base_reward, min_reward)


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
    
    base_reward = item_price * 0.10
    priority_bonus = base_reward * 0.5 if priority else 0.0
    cross_area_bonus = 20.0 if (pickup_area and drop_area and pickup_area != drop_area) else 0.0
    
    subtotal = base_reward + priority_bonus + cross_area_bonus
    final_reward = max(subtotal, 20.0)
    
    return {
        "base_reward": round(base_reward, 2),
        "priority_bonus": round(priority_bonus, 2),
        "cross_area_bonus": round(cross_area_bonus, 2),
        "subtotal": round(subtotal, 2),
        "minimum_applied": subtotal < 20.0,
        "final_reward": round(final_reward, 2),
        "formula": "10% of item_price + priority(50%) + cross_area(₹20)"
    }


# Configuration (can be moved to config.py later)
REWARD_CONFIG = {
    "base_percentage": 0.10,  # 10% of item price
    "priority_multiplier": 1.5,  # 50% bonus
    "cross_area_bonus": 20.0,  # ₹20 flat
    "minimum_reward": 20.0,  # Minimum ₹20
    "maximum_reward_percentage": 0.50,  # Max 50% of item price
}