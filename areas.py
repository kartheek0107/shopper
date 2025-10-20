"""
Area Management and Filtering System
Handles predefined areas, user preferences, and area-based filtering
"""

from typing import List, Optional, Dict
from firebase_admin import firestore
from fastapi import HTTPException

# Get Firestore client
db = firestore.client()

# Predefined areas in the college campus
PREDEFINED_AREAS = [
    "SBIT",
    "CECT",
    "Pallri",
    "Bahalgarh",
    "Sonepat",
    "TDI",
    "Lakegroove",
    "KingsBurry",
    "SuperMax"
]


def get_available_areas() -> List[str]:
    """
    Get list of all available areas
    
    Returns:
        List[str]: List of predefined areas
    """
    return PREDEFINED_AREAS.copy()


def validate_area(area: str) -> bool:
    """
    Validate if an area exists in predefined areas
    
    Args:
        area: Area name to validate
        
    Returns:
        bool: True if area is valid
    """
    return area in PREDEFINED_AREAS


def validate_areas(areas: List[str]) -> bool:
    """
    Validate multiple areas
    
    Args:
        areas: List of area names
        
    Returns:
        bool: True if all areas are valid
    """
    return all(area in PREDEFINED_AREAS for area in areas)


async def set_user_preferred_areas(user_uid: str, areas: List[str]) -> Dict:
    """
    Set user's preferred operating areas
    
    Args:
        user_uid: User UID
        areas: List of preferred areas
        
    Returns:
        dict: Updated user data
        
    Raises:
        HTTPException: If areas are invalid
    """
    if not areas:
        raise HTTPException(
            status_code=400,
            detail="At least one preferred area must be specified"
        )
    
    if not validate_areas(areas):
        invalid_areas = [a for a in areas if a not in PREDEFINED_AREAS]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid areas: {invalid_areas}. Valid areas: {PREDEFINED_AREAS}"
        )
    
    user_ref = db.collection('users').document(user_uid)
    
    from datetime import datetime
    user_ref.update({
        'preferred_areas': areas,
        'updated_at': datetime.utcnow()
    })
    
    user_doc = user_ref.get()
    return user_doc.to_dict()


async def set_user_current_area(user_uid: str, area: Optional[str]) -> Dict:
    """
    Set user's current area (optional field)
    
    Args:
        user_uid: User UID
        area: Current area (None to clear)
        
    Returns:
        dict: Updated user data
        
    Raises:
        HTTPException: If area is invalid
    """
    if area and not validate_area(area):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid area: {area}. Valid areas: {PREDEFINED_AREAS}"
        )
    
    user_ref = db.collection('users').document(user_uid)
    
    from datetime import datetime
    user_ref.update({
        'current_area': area,
        'updated_at': datetime.utcnow()
    })
    
    user_doc = user_ref.get()
    return user_doc.to_dict()


async def get_reachable_users_count(area: Optional[str] = None) -> int:
    """
    Get count of reachable users, optionally filtered by area
    
    Args:
        area: Optional area filter
        
    Returns:
        int: Count of reachable users
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_reachable', '==', True))
    
    if not area:
        return len(list(query.stream()))
    
    # Filter by preferred areas
    count = 0
    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        preferred_areas = user_data.get('preferred_areas', [])
        if area in preferred_areas:
            count += 1
    
    return count


async def get_reachable_users_by_area() -> Dict[str, int]:
    """
    Get count of reachable users grouped by area
    
    Returns:
        dict: Area name -> count mapping
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_reachable', '==', True))
    
    area_counts = {area: 0 for area in PREDEFINED_AREAS}
    
    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        preferred_areas = user_data.get('preferred_areas', [])
        
        for area in preferred_areas:
            if area in area_counts:
                area_counts[area] += 1
    
    return area_counts


async def get_available_users(
    area: Optional[str] = None,
    preferred_areas_only: bool = False
) -> List[Dict]:
    """
    Get list of available (reachable) users with optional filters
    
    Args:
        area: Filter by specific area
        preferred_areas_only: Only return users with preferred areas set
        
    Returns:
        List[dict]: List of available users
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_reachable', '==', True))
    
    available_users = []
    
    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        preferred_areas = user_data.get('preferred_areas', [])
        
        # Filter by preferred areas if required
        if preferred_areas_only and not preferred_areas:
            continue
        
        # Filter by specific area if provided
        if area and area not in preferred_areas:
            continue
        
        # Don't expose sensitive info
        available_users.append({
            'uid': user_data.get('uid'),
            'email': user_data.get('email'),
            'name': user_data.get('name'),
            'preferred_areas': preferred_areas,
            'current_area': user_data.get('current_area')
        })
    
    return available_users


async def get_requests_by_area(
    pickup_area: Optional[str] = None,
    drop_area: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict]:
    """
    Get requests filtered by pickup/drop areas
    
    Args:
        pickup_area: Filter by pickup area
        drop_area: Filter by drop area
        status: Filter by status
        
    Returns:
        List[dict]: Filtered requests
    """
    requests_ref = db.collection('requests')
    
    # Start with base query
    if status:
        query = requests_ref.where(filter=firestore.FieldFilter('status', '==', status))
    else:
        query = requests_ref
    
    # Get all and filter in memory (Firestore doesn't support complex OR queries well)
    requests = []
    for doc in query.stream():
        request_data = doc.to_dict()
        
        # Filter by pickup area
        if pickup_area and request_data.get('pickup_area') != pickup_area:
            continue
        
        # Filter by drop area
        if drop_area and request_data.get('drop_area') != drop_area:
            continue
        
        requests.append(request_data)
    
    # Sort by creation time (newest first)
    requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return requests


async def get_nearby_requests(user_uid: str) -> List[Dict]:
    """
    Get requests near user's current or preferred areas
    
    Args:
        user_uid: User UID
        
    Returns:
        List[dict]: Nearby open requests
    """
    # Get user's areas
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return []
    
    user_data = user_doc.to_dict()
    preferred_areas = user_data.get('preferred_areas', [])
    current_area = user_data.get('current_area')
    
    # Combine current and preferred areas
    user_areas = set(preferred_areas)
    if current_area:
        user_areas.add(current_area)
    
    if not user_areas:
        return []
    
    # Get open requests
    requests_ref = db.collection('requests')
    query = requests_ref.where(filter=firestore.FieldFilter('status', '==', 'open'))
    
    nearby_requests = []
    for doc in query.stream():
        request_data = doc.to_dict()
        
        # Skip own requests
        if request_data.get('posted_by') == user_uid:
            continue
        
        pickup_area = request_data.get('pickup_area')
        drop_area = request_data.get('drop_area')
        
        # Check if request involves any of user's areas
        if pickup_area in user_areas or drop_area in user_areas:
            nearby_requests.append(request_data)
    
    # Sort by creation time (newest first)
    nearby_requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return nearby_requests