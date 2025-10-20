"""
Connectivity and Reachability Management System
Handles user connectivity status, location permissions, and auto-computed reachability
"""

from typing import Dict
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
    location_permission_granted: bool
) -> Dict:
    """
    Update user's connectivity status and auto-compute reachability
    
    Args:
        user_uid: User UID
        is_connected: Whether device is connected to internet
        location_permission_granted: Whether location permission is granted
        
    Returns:
        dict: Updated user data with reachability status
    """
    user_ref = db.collection('users').document(user_uid)
    
    # Calculate reachability
    is_reachable = calculate_reachability(is_connected, location_permission_granted)
    
    # Update user document
    update_data = {
        'is_connected': is_connected,
        'location_permission_granted': location_permission_granted,
        'is_reachable': is_reachable,
        'last_connectivity_check': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    user_ref.update(update_data)
    
    # Get and return updated user data
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user_doc.to_dict()


async def get_reachability_status(user_uid: str) -> Dict:
    """
    Get current reachability status for a user
    
    Args:
        user_uid: User UID
        
    Returns:
        dict: Reachability status information
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
    Get overall connectivity statistics
    
    Returns:
        dict: Statistics about user connectivity
    """
    users_ref = db.collection('users')
    
    total_users = 0
    reachable_users = 0
    connected_users = 0
    location_granted_users = 0
    
    for user_doc in users_ref.stream():
        user_data = user_doc.to_dict()
        total_users += 1
        
        if user_data.get('is_reachable'):
            reachable_users += 1
        if user_data.get('is_connected'):
            connected_users += 1
        if user_data.get('location_permission_granted'):
            location_granted_users += 1
    
    return {
        'total_users': total_users,
        'reachable_users': reachable_users,
        'connected_users': connected_users,
        'location_granted_users': location_granted_users,
        'reachable_percentage': round((reachable_users / total_users * 100), 2) if total_users > 0 else 0
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