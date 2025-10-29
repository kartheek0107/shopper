"""
Connectivity and Reachability Management System with Device Tracking
Handles user connectivity status, location permissions, device tracking, and auto-computed reachability
"""

from typing import Dict, List, Optional
from firebase_admin import firestore
from datetime import datetime
from fastapi import HTTPException

# Get Firestore client
db = firestore.client()


def calculate_reachability(
    is_connected: bool,
    location_permission_granted: bool
) -> bool:
    """
    Calculate if user is reachable based on connectivity and permissions
    
    User is reachable if BOTH conditions are true:
    1. Connected to internet
    2. Location permission granted
    
    Args:
        is_connected: Whether device has internet connectivity
        location_permission_granted: Whether location permission is granted
        
    Returns:
        bool: True if user is reachable
    """
    return is_connected and location_permission_granted


async def update_connectivity_status(
    user_uid: str,
    is_connected: bool,
    location_permission_granted: bool,
    device_id: Optional[str] = None,
    device_info: Optional[dict] = None
) -> Dict:
    """
    Update user's connectivity status and auto-compute reachability with device tracking
    
    Changes:
    - Now accepts optional device_id and device_info parameters
    - Stores device information for multi-device user tracking
    - Maintains backward compatibility (device_id is optional)
    
    Args:
        user_uid: User UID
        is_connected: Whether device is connected to internet
        location_permission_granted: Whether location permission is granted
        device_id: Optional unique device identifier
        device_info: Optional device metadata (OS, model, app version)
        
    Returns:
        dict: Updated user data with reachability status
    """
    user_ref = db.collection('users').document(user_uid)
    
    # Calculate reachability
    is_reachable = calculate_reachability(is_connected, location_permission_granted)
    
    # Prepare update data
    update_data = {
        'is_connected': is_connected,
        'location_permission_granted': location_permission_granted,
        'is_reachable': is_reachable,
        'last_connectivity_check': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    # Add device tracking if device_id provided
    if device_id:
        update_data['device_id'] = device_id
        
        # First time device registration
        user_doc = user_ref.get()
        if user_doc.exists:
            existing_device_id = user_doc.to_dict().get('device_id')
            if not existing_device_id:
                update_data['device_registered_at'] = datetime.utcnow()
        
        # Store device info if provided
        if device_info:
            update_data['device_info'] = device_info
    
    # Update user document
    user_ref.update(update_data)
    
    # Get and return updated user data
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user_doc.to_dict()


async def get_reachability_status(user_uid: str) -> Dict:
    """
    Get current reachability status for a user with device information
    
    Args:
        user_uid: User UID
        
    Returns:
        dict: Reachability status information including device_id
    """
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user_doc.to_dict()
    
    return {
        'is_reachable': user_data.get('is_reachable', False),
        'is_connected': user_data.get('is_connected', False),
        'location_permission_granted': user_data.get('location_permission_granted', False),
        'last_connectivity_check': user_data.get('last_connectivity_check'),
        'device_id': user_data.get('device_id'),  # NEW
        'device_info': user_data.get('device_info'),  # NEW
        'message': 'Reachable' if user_data.get('is_reachable') else 'Not reachable'
    }


async def force_update_reachability(user_uid: str, is_reachable: bool) -> Dict:
    """
    Manually override reachability status (admin use or special cases)
    
    Args:
        user_uid: User UID
        is_reachable: New reachability status
        
    Returns:
        dict: Updated user data
    """
    user_ref = db.collection('users').document(user_uid)
    
    user_ref.update({
        'is_reachable': is_reachable,
        'updated_at': datetime.utcnow()
    })
    
    user_doc = user_ref.get()
    return user_doc.to_dict()


async def get_connectivity_stats() -> Dict:
    """
    Get overall connectivity statistics with device tracking
    
    Changes:
    - Now includes unique device count
    - Identifies users with multiple devices
    
    Returns:
        dict: Statistics about user connectivity and device usage
    """
    users_ref = db.collection('users')
    
    total_users = 0
    reachable_users = 0
    connected_users = 0
    location_granted_users = 0
    
    # Device tracking
    unique_devices = set()
    users_with_devices = 0
    device_to_users = {}  # Track if device_id is used by multiple UIDs
    
    for user_doc in users_ref.stream():
        user_data = user_doc.to_dict()
        user_uid = user_data.get('uid')
        total_users += 1
        
        # Connectivity stats
        if user_data.get('is_reachable'):
            reachable_users += 1
        if user_data.get('is_connected'):
            connected_users += 1
        if user_data.get('location_permission_granted'):
            location_granted_users += 1
        
        # Device tracking
        device_id = user_data.get('device_id')
        if device_id:
            users_with_devices += 1
            unique_devices.add(device_id)
            
            # Track multiple users per device (edge case detection)
            if device_id not in device_to_users:
                device_to_users[device_id] = []
            device_to_users[device_id].append(user_uid)
    
    # Count multi-device users (same device_id, different UIDs - shouldn't happen normally)
    multi_device_users = sum(1 for users in device_to_users.values() if len(users) > 1)
    
    return {
        'total_users': total_users,
        'reachable_users': reachable_users,
        'connected_users': connected_users,
        'location_granted_users': location_granted_users,
        'reachable_percentage': round((reachable_users / total_users * 100), 2) if total_users > 0 else 0,
        'unique_devices': len(unique_devices),  # NEW
        'users_with_devices': users_with_devices,  # NEW
        'multi_device_users': multi_device_users  # NEW (edge case indicator)
    }


async def get_unique_reachable_devices(area: Optional[str] = None) -> Dict:
    """
    Get count of unique reachable devices (not just users)
    
    This is useful for:
    - Accurate delivery person availability
    - Preventing double-counting if same user has multiple accounts
    - Better capacity planning
    
    Args:
        area: Optional area filter
        
    Returns:
        dict: Unique device count and user count comparison
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_reachable', '==', True))
    
    unique_devices = set()
    total_users = 0
    users_without_device_id = 0
    
    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        total_users += 1
        
        # Filter by area if specified
        if area:
            preferred_areas = user_data.get('preferred_areas', [])
            if area not in preferred_areas:
                continue
        
        device_id = user_data.get('device_id')
        if device_id:
            unique_devices.add(device_id)
        else:
            users_without_device_id += 1
            # Fallback: count user without device_id as unique
            unique_devices.add(user_data.get('uid'))
    
    return {
        'unique_devices': len(unique_devices),
        'total_reachable_users': total_users,
        'users_without_device_id': users_without_device_id,
        'area': area or 'all',
        'note': 'Users without device_id are counted by UID for backward compatibility'
    }


async def check_stale_connectivity(minutes: int = 10) -> list:
    """
    Find users whose connectivity hasn't been checked recently
    
    Args:
        minutes: Number of minutes to consider stale
        
    Returns:
        list: UIDs of users with stale connectivity
    """
    users_ref = db.collection('users')
    cutoff_time = datetime.utcnow().timestamp() - (minutes * 60)
    
    stale_users = []
    
    for user_doc in users_ref.stream():
        user_data = user_doc.to_dict()
        last_check = user_data.get('last_connectivity_check')
        
        if not last_check or last_check.timestamp() < cutoff_time:
            stale_users.append(user_data.get('uid'))
    
    return stale_users


async def get_device_analytics() -> Dict:
    """
    Get analytics about device usage patterns
    
    Returns:
        dict: Device analytics including OS distribution, multi-account detection
    """
    users_ref = db.collection('users')
    
    device_info_map = {}
    os_distribution = {}
    
    for user_doc in users_ref.stream():
        user_data = user_doc.to_dict()
        device_info = user_data.get('device_info')
        
        if device_info:
            # OS distribution
            os_type = device_info.get('os', 'Unknown')
            os_distribution[os_type] = os_distribution.get(os_type, 0) + 1
            
            # Store device info
            device_id = user_data.get('device_id')
            if device_id:
                if device_id not in device_info_map:
                    device_info_map[device_id] = []
                device_info_map[device_id].append({
                    'uid': user_data.get('uid'),
                    'email': user_data.get('email'),
                    'device_info': device_info
                })
    
    return {
        'total_devices_tracked': len(device_info_map),
        'os_distribution': os_distribution,
        'devices_with_multiple_accounts': sum(1 for users in device_info_map.values() if len(users) > 1)
    }