"""
Area Management and Filtering System with Device-based Counting
FIXED: Now uses GPS-detected areas (current_area) instead of preferred_areas
"""

from typing import List, Optional, Dict
from firebase_admin import firestore
from fastapi import HTTPException

# Get Firestore client
db = firestore.client()

# Predefined areas in the college campus
PREDEFINED_AREAS = [
    "SBIT",
    "Pallri",
    "Bahalgarh",
    "Sonepat",
    "TDI",
    "New Delhi"
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


async def get_reachable_users_count(
    area: Optional[str] = None,
    count_by_device: bool = True
) -> int:
    """
    Get count of reachable users, optionally filtered by GPS-detected area
    
    FIXED: Now uses current_area (GPS-detected) instead of preferred_areas
    
    A user is "reachable" if:
    1. is_connected = True (has internet)
    2. location_permission_granted = True (app can track location)
    3. Has a current_area set (GPS location was processed)
    
    Args:
        area: Optional area filter (uses GPS-detected area)
        count_by_device: If True, count unique devices; if False, count users
        
    Returns:
        int: Count of reachable users or unique devices
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_connected', '==', True))
    
    if not count_by_device:
        # Original logic: count all users
        count = 0
        for user_doc in query.stream():
            user_data = user_doc.to_dict()
            
            # Check location permission
            if not user_data.get('location_permission_granted', False):
                continue
            
            # Get GPS-detected area
            current_area = user_data.get('current_area')
            
            # Skip if no area or "_nearby" area
            if not current_area or current_area.endswith('_nearby'):
                continue
            
            # Filter by area if specified
            if area and current_area != area:
                continue
            
            count += 1
        
        return count
    
    # Device-based counting
    unique_identifiers = set()
    
    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        
        # Check location permission
        if not user_data.get('location_permission_granted', False):
            continue
        
        # Get GPS-detected area
        current_area = user_data.get('current_area')
        
        # Skip if no area or "_nearby" area
        if not current_area or current_area.endswith('_nearby'):
            continue
        
        # Filter by area if specified
        if area and current_area != area:
            continue
        
        # Use device_id if available, otherwise fallback to uid
        identifier = user_data.get('device_id') or user_data.get('uid')
        if identifier:
            unique_identifiers.add(identifier)
    
    return len(unique_identifiers)


async def get_reachable_users_by_area(count_by_device: bool = True) -> Dict[str, int]:
    """
    Get count of reachable users grouped by their GPS-detected area
    
    FIXED: Now uses current_area (GPS-detected) instead of preferred_areas
    
    A user is "reachable" if:
    1. is_connected = True (has internet)
    2. location_permission_granted = True (app can track location)
    3. Has a current_area set (GPS location was processed)
    
    Args:
        count_by_device: If True, count unique devices per area
        
    Returns:
        dict: Area name -> count mapping
    """
    users_ref = db.collection('users')
    
    # Query for reachable users with connectivity
    query_connected = users_ref.where(filter=firestore.FieldFilter('is_connected', '==', True))
    
    if count_by_device:
        # Device-based counting per area
        area_device_sets = {area: set() for area in PREDEFINED_AREAS}
        
        for user_doc in query_connected.stream():
            user_data = user_doc.to_dict()
            
            # Check all reachability conditions
            if not user_data.get('location_permission_granted', False):
                continue
            
            # Get GPS-detected area (current_area)
            current_area = user_data.get('current_area')
            
            # Skip if no area detected or area ends with "_nearby"
            if not current_area or current_area.endswith('_nearby'):
                continue
            
            # Get unique identifier (device_id or uid)
            identifier = user_data.get('device_id') or user_data.get('uid')
            
            if identifier and current_area in area_device_sets:
                area_device_sets[current_area].add(identifier)
        
        return {area: len(devices) for area, devices in area_device_sets.items()}
    
    else:
        # User-based counting per area
        area_counts = {area: 0 for area in PREDEFINED_AREAS}
        
        for user_doc in query_connected.stream():
            user_data = user_doc.to_dict()
            
            # Check all reachability conditions
            if not user_data.get('location_permission_granted', False):
                continue
            
            # Get GPS-detected area
            current_area = user_data.get('current_area')
            
            # Skip if no area detected or area ends with "_nearby"
            if not current_area or current_area.endswith('_nearby'):
                continue
            
            if current_area in area_counts:
                area_counts[current_area] += 1
        
        return area_counts


async def get_available_users(
    area: Optional[str] = None,
    preferred_areas_only: bool = False
) -> List[Dict]:
    """
    Get list of available (reachable) users with optional filters
    
    UPDATED: Uses GPS-detected current_area for filtering
    
    Args:
        area: Filter by specific GPS-detected area
        preferred_areas_only: Only return users with preferred areas set
        
    Returns:
        List[dict]: List of available users with device info
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_connected', '==', True))
    
    available_users = []
    
    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        
        # Check location permission
        if not user_data.get('location_permission_granted', False):
            continue
        
        # Get GPS-detected area
        current_area = user_data.get('current_area')
        
        # Skip if no area or "_nearby" area
        if not current_area or current_area.endswith('_nearby'):
            continue
        
        preferred_areas = user_data.get('preferred_areas', [])
        
        # Filter by preferred areas if required
        if preferred_areas_only and not preferred_areas:
            continue
        
        # Filter by specific area if provided (using GPS-detected area)
        if area and current_area != area:
            continue
        
        # Include device info in response
        available_users.append({
            'uid': user_data.get('uid'),
            'email': user_data.get('email'),
            'name': user_data.get('name'),
            'preferred_areas': preferred_areas,
            'current_area': current_area,
            'device_id': user_data.get('device_id'),
            'device_info': user_data.get('device_info')
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
    
    # Get all and filter in memory
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
    Get requests near user's GPS-detected area
    
    UPDATED: Uses GPS-detected current_area instead of preferred_areas
    
    Args:
        user_uid: User UID
        
    Returns:
        List[dict]: Nearby open requests
    """
    # Get user's GPS-detected area
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return []
    
    user_data = user_doc.to_dict()
    current_area = user_data.get('current_area')
    preferred_areas = user_data.get('preferred_areas', [])
    
    # Combine current GPS area and preferred areas
    user_areas = set(preferred_areas)
    if current_area and not current_area.endswith('_nearby'):
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


async def get_area_device_analytics() -> Dict:
    """
    Get analytics about device distribution across GPS-detected areas
    
    UPDATED: Uses current_area (GPS-detected) instead of preferred_areas
    
    Returns:
        dict: Device analytics per area
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_connected', '==', True))
    
    area_analytics = {area: {
        'unique_devices': set(),
        'total_users': 0,
        'users_without_device': 0
    } for area in PREDEFINED_AREAS}
    
    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        
        # Check location permission
        if not user_data.get('location_permission_granted', False):
            continue
        
        # Get GPS-detected area
        current_area = user_data.get('current_area')
        
        # Skip if no area or "_nearby" area
        if not current_area or current_area.endswith('_nearby'):
            continue
        
        device_id = user_data.get('device_id')
        
        if current_area in area_analytics:
            area_analytics[current_area]['total_users'] += 1
            
            if device_id:
                area_analytics[current_area]['unique_devices'].add(device_id)
            else:
                area_analytics[current_area]['users_without_device'] += 1
    
    # Convert sets to counts
    result = {}
    for area, data in area_analytics.items():
        result[area] = {
            'unique_devices': len(data['unique_devices']),
            'total_users': data['total_users'],
            'users_without_device': data['users_without_device'],
            'device_coverage_pct': round(
                (len(data['unique_devices']) / data['total_users'] * 100) 
                if data['total_users'] > 0 else 0, 
                2
            )
        }
    
    return result