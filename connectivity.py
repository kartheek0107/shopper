"""
Connectivity and Reachability Management System with Device Tracking

Production-hardened:
- All Firestore I/O is async (non-blocking event loop)
- Timezone-aware timestamps throughout
- device_id validation with proper error propagation
"""

from typing import Dict, List, Optional
from fastapi import HTTPException
import re

from firebase_admin import firestore as _fs
from firestore_async import (
    get_db, utcnow,
    get_doc, update_doc,
    build_query, stream_query, stream_query_snapshots,
)


def calculate_reachability(
    is_connected: bool,
    location_permission_granted: bool
) -> bool:
    """Calculate if user is reachable."""
    return is_connected and location_permission_granted


def _validate_device_id(device_id: Optional[str]) -> Optional[str]:
    """
    Validate and normalize device_id.
    Returns cleaned device_id or None if blank/missing.
    Raises HTTPException for invalid format.
    """
    if not device_id:
        return None

    device_id = device_id.strip()
    if not device_id:
        return None

    if len(device_id) < 5 or len(device_id) > 255:
        raise HTTPException(
            status_code=400,
            detail="device_id must be between 5 and 255 characters"
        )

    if not re.match(r'^[a-zA-Z0-9_\-]+$', device_id):
        raise HTTPException(
            status_code=400,
            detail="device_id can only contain letters, numbers, hyphens, and underscores"
        )

    return device_id


async def update_connectivity_status(
    user_uid: str,
    is_connected: bool,
    location_permission_granted: bool,
    device_id: Optional[str] = None,
    device_info: Optional[dict] = None
) -> Dict:
    """
    Update user's connectivity status and auto-compute reachability with device tracking.
    """
    validated_device_id = _validate_device_id(device_id)

    user_data = await get_doc('users', user_uid)
    if user_data is None:
        raise HTTPException(status_code=404, detail="User not found")

    is_reachable = calculate_reachability(is_connected, location_permission_granted)
    now = utcnow()

    update_data = {
        'is_connected': is_connected,
        'location_permission_granted': location_permission_granted,
        'is_reachable': is_reachable,
        'last_connectivity_check': now,
        'updated_at': now,
    }

    if validated_device_id:
        update_data['device_id'] = validated_device_id

        # First time device registration
        if not user_data.get('device_id'):
            update_data['device_registered_at'] = now

        # Store device info if provided (only allowed keys)
        if device_info:
            if hasattr(device_info, 'model_dump'):
                device_info = device_info.model_dump()
            allowed_keys = {'os', 'model', 'app_version', 'manufacturer'}
            filtered_info = {k: v for k, v in device_info.items() if k in allowed_keys}
            if filtered_info:
                update_data['device_info'] = filtered_info

    await update_doc('users', user_uid, update_data)

    # Invalidate count cache since reachability changed
    from areas import invalidate_count_cache
    await invalidate_count_cache()

    # Return merged data so callers get a complete picture
    user_data.update(update_data)
    return user_data


async def get_reachability_status(user_uid: str) -> Dict:
    """Get current reachability status for a user."""
    user_data = await get_doc('users', user_uid)
    if user_data is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        'is_reachable': user_data.get('is_reachable', False),
        'is_connected': user_data.get('is_connected', False),
        'location_permission_granted': user_data.get('location_permission_granted', False),
        'last_connectivity_check': user_data.get('last_connectivity_check'),
        'device_id': user_data.get('device_id'),
        'device_info': user_data.get('device_info'),
        'message': 'Reachable' if user_data.get('is_reachable') else 'Not reachable',
    }


async def force_update_reachability(user_uid: str, is_reachable: bool) -> Dict:
    """Manually override reachability status."""
    await update_doc('users', user_uid, {
        'is_reachable': is_reachable,
        'updated_at': utcnow(),
    })

    from areas import invalidate_count_cache
    await invalidate_count_cache()

    return await get_doc('users', user_uid)


async def get_connectivity_stats() -> Dict:
    """Get overall connectivity statistics with device tracking (cached 60s)."""
    from redis_cache import cache_get, cache_set
    from areas import _is_connection_fresh

    cache_key = "connectivity:stats"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    q = build_query('users')
    all_users = await stream_query(q)

    total_users = 0
    reachable_users = 0
    connected_users = 0
    location_granted_users = 0
    unique_devices = set()
    users_with_devices = 0
    device_to_users = {}
    stale_connections = 0

    for user_data in all_users:
        user_uid = user_data.get('uid')
        total_users += 1

        last_check = user_data.get('last_connectivity_check')
        if user_data.get('is_connected') and not _is_connection_fresh(last_check):
            stale_connections += 1
            continue

        if user_data.get('is_reachable'):
            reachable_users += 1
        if user_data.get('is_connected'):
            connected_users += 1
        if user_data.get('location_permission_granted'):
            location_granted_users += 1

        device_id = user_data.get('device_id')
        if device_id and device_id.strip():
            users_with_devices += 1
            unique_devices.add(device_id)
            if device_id not in device_to_users:
                device_to_users[device_id] = []
            device_to_users[device_id].append(user_uid)

    multi_device_users = sum(1 for users in device_to_users.values() if len(users) > 1)

    result = {
        'total_users': total_users,
        'reachable_users': reachable_users,
        'connected_users': connected_users,
        'location_granted_users': location_granted_users,
        'stale_connections': stale_connections,
        'reachable_percentage': round((reachable_users / total_users * 100), 2) if total_users > 0 else 0,
        'unique_devices': len(unique_devices),
        'users_with_devices': users_with_devices,
        'multi_device_users': multi_device_users,
    }

    await cache_set(cache_key, result, ttl_seconds=60)
    return result


async def get_unique_reachable_devices(area: Optional[str] = None) -> Dict:
    """Get count of unique reachable devices."""
    from areas import _is_connection_fresh, _should_include_user_area

    q = build_query('users', filters=[('is_reachable', '==', True)])
    all_users = await stream_query(q)

    unique_devices = set()
    total_users = 0
    users_without_device_id = 0

    for user_data in all_users:
        last_check = user_data.get('last_connectivity_check')
        if not _is_connection_fresh(last_check):
            continue

        total_users += 1

        if area:
            current_area = user_data.get('current_area')
            if not _should_include_user_area(current_area, area, include_nearby=True):
                continue

        device_id = user_data.get('device_id')
        if device_id and device_id.strip():
            unique_devices.add(device_id)
        else:
            users_without_device_id += 1
            unique_devices.add(user_data.get('uid'))

    return {
        'unique_devices': len(unique_devices),
        'total_reachable_users': total_users,
        'users_without_device_id': users_without_device_id,
        'area': area or 'all',
        'note': 'Users without device_id are counted by UID for backward compatibility',
    }


async def check_stale_connectivity(minutes: int = 10) -> list:
    """Find users whose connectivity hasn't been checked recently."""
    now = utcnow()
    cutoff_timestamp = now.timestamp() - (minutes * 60)

    q = build_query('users')
    all_users = await stream_query(q)

    stale_users = []
    for user_data in all_users:
        last_check = user_data.get('last_connectivity_check')
        if not last_check or last_check.timestamp() < cutoff_timestamp:
            stale_users.append({
                'uid': user_data.get('uid'),
                'email': user_data.get('email'),
                'last_check': last_check.isoformat() if last_check else None,
                'is_connected': user_data.get('is_connected', False),
            })

    return stale_users


async def get_device_analytics() -> Dict:
    """Get analytics about device usage patterns."""
    q = build_query('users')
    all_users = await stream_query(q)

    device_info_map = {}
    os_distribution = {}

    for user_data in all_users:
        device_info = user_data.get('device_info')
        if device_info:
            os_type = device_info.get('os', 'Unknown')
            os_distribution[os_type] = os_distribution.get(os_type, 0) + 1

            device_id = user_data.get('device_id')
            if device_id:
                if device_id not in device_info_map:
                    device_info_map[device_id] = []
                device_info_map[device_id].append({
                    'uid': user_data.get('uid'),
                    'email': user_data.get('email'),
                    'device_info': device_info,
                })

    return {
        'total_devices_tracked': len(device_info_map),
        'os_distribution': os_distribution,
        'devices_with_multiple_accounts': sum(
            1 for users in device_info_map.values() if len(users) > 1
        ),
    }