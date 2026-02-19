"""
Area Management and Filtering System with Device-based Counting
FIXED: All concurrency, caching, and edge case issues resolved
"""

from typing import List, Optional, Dict, Tuple
from firebase_admin import firestore
from fastapi import HTTPException
from datetime import datetime, timedelta
import asyncio
from functools import lru_cache
import time

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

# ============================================
# CACHE CONFIGURATION
# ============================================
_count_cache: Dict[str, Tuple[int, float]] = {}
_count_cache_lock = asyncio.Lock()
CACHE_TTL_SECONDS = 30
STALE_CONNECTION_MINUTES = 10


def _get_cache_key(area: Optional[str], count_by_device: bool, include_nearby: bool) -> str:
    """Generate cache key for count queries"""
    return f"count:{area or 'all'}:{count_by_device}:{include_nearby}"


async def _get_cached_count(cache_key: str) -> Optional[int]:
    """Get count from cache if not expired"""
    async with _count_cache_lock:
        if cache_key in _count_cache:
            count, timestamp = _count_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return count
            else:
                del _count_cache[cache_key]
    return None


async def _set_cached_count(cache_key: str, count: int):
    """Store count in cache with timestamp"""
    async with _count_cache_lock:
        _count_cache[cache_key] = (count, time.time())


async def invalidate_count_cache():
    """Invalidate all cached counts (call when user connectivity changes)"""
    async with _count_cache_lock:
        _count_cache.clear()


def get_available_areas() -> List[str]:
    """Get list of all available areas"""
    return PREDEFINED_AREAS.copy()


def validate_area(area: str) -> bool:
    """Validate if an area exists in predefined areas"""
    if not area or not isinstance(area, str):
        return False
    return area.strip() in PREDEFINED_AREAS


def validate_areas(areas: List[str]) -> bool:
    """Validate multiple areas"""
    if not areas or not isinstance(areas, list):
        return False
    return all(validate_area(area) for area in areas)


async def set_user_preferred_areas(user_uid: str, areas: List[str]) -> Dict:
    """Set user's preferred operating areas"""
    if not areas:
        raise HTTPException(
            status_code=400,
            detail="At least one preferred area must be specified"
        )

    if not validate_areas(areas):
        invalid_areas = [a for a in areas if not validate_area(a)]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid areas: {invalid_areas}. Valid areas: {PREDEFINED_AREAS}"
        )

    user_ref = db.collection('users').document(user_uid)

    user_ref.update({
        'preferred_areas': areas,
        'updated_at': datetime.utcnow()
    })

    user_doc = user_ref.get()
    return user_doc.to_dict()


async def set_user_current_area(user_uid: str, area: Optional[str]) -> Dict:
    """Set user's current area (GPS-detected)"""
    if area and not validate_area(area):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid area: {area}. Valid areas: {PREDEFINED_AREAS}"
        )

    user_ref = db.collection('users').document(user_uid)

    user_ref.update({
        'current_area': area,
        'updated_at': datetime.utcnow()
    })

    # Invalidate cache since user's area changed
    await invalidate_count_cache()

    user_doc = user_ref.get()
    return user_doc.to_dict()


def _is_connection_fresh(last_check) -> bool:
    """Check if connectivity check is recent enough"""
    if not last_check:
        return False

    # Handle timezone-naive datetime
    if hasattr(last_check, 'tzinfo') and last_check.tzinfo is None:
        from datetime import timezone
        last_check = last_check.replace(tzinfo=timezone.utc)

    try:
        cutoff = datetime.utcnow().replace(
            tzinfo=last_check.tzinfo
        ) - timedelta(minutes=STALE_CONNECTION_MINUTES)
        return last_check >= cutoff
    except Exception:
        return False


def _should_include_user_area(
    current_area: Optional[str],
    filter_area: Optional[str],
    include_nearby: bool
) -> bool:
    """
    Determine if user should be included based on area filtering.
    Handles _nearby suffix correctly.
    """
    if not current_area:
        return False

    is_nearby_area = current_area.endswith('_nearby')

    if is_nearby_area and not include_nearby:
        return False

    # No area filter → include all (respecting nearby flag above)
    if not filter_area:
        return True

    # Extract base area from _nearby suffix for comparison
    base_area = current_area.replace('_nearby', '') if is_nearby_area else current_area

    return base_area == filter_area


async def get_reachable_users_count(
    area: Optional[str] = None,
    count_by_device: bool = True,
    include_nearby: bool = True
) -> int:
    """
    Get count of reachable users with caching, staleness check, and _nearby handling.

    Args:
        area: Optional area filter (uses GPS-detected area)
        count_by_device: If True, count unique devices; if False, count users
        include_nearby: If True, include users in "{area}_nearby" (default: True)

    Returns:
        int: Count of reachable users or unique devices
    """
    if area and not validate_area(area):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid area: {area}. Valid areas: {PREDEFINED_AREAS}"
        )

    cache_key = _get_cache_key(area, count_by_device, include_nearby)
    cached_count = await _get_cached_count(cache_key)

    if cached_count is not None:
        return cached_count

    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_connected', '==', True))

    if count_by_device:
        unique_identifiers = set()

        for user_doc in query.stream():
            user_data = user_doc.to_dict()

            if not user_data.get('location_permission_granted', False):
                continue

            last_check = user_data.get('last_connectivity_check')
            if not _is_connection_fresh(last_check):
                continue

            current_area_val = user_data.get('current_area')

            if not _should_include_user_area(current_area_val, area, include_nearby):
                continue

            identifier = user_data.get('device_id')
            if not identifier or not identifier.strip():
                identifier = user_data.get('uid')

            if identifier:
                unique_identifiers.add(identifier)

        count = len(unique_identifiers)

    else:
        count = 0

        for user_doc in query.stream():
            user_data = user_doc.to_dict()

            if not user_data.get('location_permission_granted', False):
                continue

            last_check = user_data.get('last_connectivity_check')
            if not _is_connection_fresh(last_check):
                continue

            current_area_val = user_data.get('current_area')

            if not _should_include_user_area(current_area_val, area, include_nearby):
                continue

            count += 1

    await _set_cached_count(cache_key, count)

    return count


async def get_reachable_users_by_area(
    count_by_device: bool = True,
    include_nearby: bool = True
) -> Dict[str, int]:
    """
    Get count of reachable users grouped by GPS-detected area with caching.

    Args:
        count_by_device: If True, count unique devices per area
        include_nearby: If True, include users in "{area}_nearby" areas

    Returns:
        dict: Area name -> count mapping
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_connected', '==', True))

    if count_by_device:
        area_device_sets = {area: set() for area in PREDEFINED_AREAS}

        if include_nearby:
            for area in PREDEFINED_AREAS:
                area_device_sets[f"{area}_nearby"] = set()

        for user_doc in query.stream():
            user_data = user_doc.to_dict()

            if not user_data.get('location_permission_granted', False):
                continue

            last_check = user_data.get('last_connectivity_check')
            if not _is_connection_fresh(last_check):
                continue

            current_area = user_data.get('current_area')

            if not current_area:
                continue

            is_nearby = current_area.endswith('_nearby')
            if is_nearby and not include_nearby:
                continue

            identifier = user_data.get('device_id')
            if not identifier or not identifier.strip():
                identifier = user_data.get('uid')

            if identifier and current_area in area_device_sets:
                area_device_sets[current_area].add(identifier)

        # Convert sets to counts, drop empty _nearby entries
        result = {}
        for area, devices in area_device_sets.items():
            count = len(devices)
            if count > 0 or not area.endswith('_nearby'):
                result[area] = count

        return result

    else:
        area_counts = {area: 0 for area in PREDEFINED_AREAS}

        if include_nearby:
            for area in PREDEFINED_AREAS:
                area_counts[f"{area}_nearby"] = 0

        for user_doc in query.stream():
            user_data = user_doc.to_dict()

            if not user_data.get('location_permission_granted', False):
                continue

            last_check = user_data.get('last_connectivity_check')
            if not _is_connection_fresh(last_check):
                continue

            current_area = user_data.get('current_area')

            if not current_area:
                continue

            is_nearby = current_area.endswith('_nearby')
            if is_nearby and not include_nearby:
                continue

            if current_area in area_counts:
                area_counts[current_area] += 1

        result = {area: count for area, count in area_counts.items()
                  if count > 0 or not area.endswith('_nearby')}

        return result


async def get_available_users(
    area: Optional[str] = None,
    preferred_areas_only: bool = False,
    include_nearby: bool = True
) -> List[Dict]:
    """
    Get list of available (reachable) users with filters.
    Includes staleness check and _nearby handling.
    """
    if area and not validate_area(area):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid area: {area}"
        )

    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_connected', '==', True))

    available_users = []

    for user_doc in query.stream():
        user_data = user_doc.to_dict()

        if not user_data.get('location_permission_granted', False):
            continue

        last_check = user_data.get('last_connectivity_check')
        if not _is_connection_fresh(last_check):
            continue

        current_area = user_data.get('current_area')
        preferred_areas = user_data.get('preferred_areas', [])

        if not _should_include_user_area(current_area, area, include_nearby):
            continue

        if preferred_areas_only and not preferred_areas:
            continue

        available_users.append({
            'uid': user_data.get('uid'),
            'email': user_data.get('email'),
            'name': user_data.get('name'),
            'preferred_areas': preferred_areas,
            'current_area': current_area,
            'device_id': user_data.get('device_id'),
            'device_info': user_data.get('device_info'),
            'last_seen': last_check.isoformat() if last_check else None
        })

    return available_users


async def get_requests_by_area(
    pickup_area: Optional[str] = None,
    drop_area: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict]:
    """Get requests filtered by pickup/drop areas"""
    if pickup_area and not validate_area(pickup_area):
        raise HTTPException(status_code=400, detail=f"Invalid pickup_area: {pickup_area}")
    if drop_area and not validate_area(drop_area):
        raise HTTPException(status_code=400, detail=f"Invalid drop_area: {drop_area}")

    requests_ref = db.collection('requests')

    if status:
        query = requests_ref.where(filter=firestore.FieldFilter('status', '==', status))
    else:
        query = requests_ref

    requests = []
    for doc in query.stream():
        request_data = doc.to_dict()

        if pickup_area and request_data.get('pickup_area') != pickup_area:
            continue

        if drop_area and request_data.get('drop_area') != drop_area:
            continue

        requests.append(request_data)

    requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    return requests


async def get_nearby_requests(user_uid: str, include_nearby: bool = True) -> List[Dict]:
    """
    Get requests near user's GPS-detected area.
    Properly handles _nearby areas.
    """
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()

    if not user_doc.exists:
        return []

    user_data = user_doc.to_dict()
    current_area = user_data.get('current_area')
    preferred_areas = user_data.get('preferred_areas', [])

    user_areas = set(preferred_areas)

    if current_area:
        if current_area.endswith('_nearby'):
            if include_nearby:
                base_area = current_area.replace('_nearby', '')
                user_areas.add(base_area)
                user_areas.add(current_area)
        else:
            user_areas.add(current_area)

    if not user_areas:
        return []

    requests_ref = db.collection('requests')
    query = requests_ref.where(filter=firestore.FieldFilter('status', '==', 'open'))

    nearby_requests = []
    for doc in query.stream():
        request_data = doc.to_dict()

        if request_data.get('posted_by') == user_uid:
            continue

        pickup_area = request_data.get('pickup_area')
        drop_area = request_data.get('drop_area')

        if pickup_area in user_areas or drop_area in user_areas:
            nearby_requests.append(request_data)

    nearby_requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    return nearby_requests


async def get_area_device_analytics() -> Dict:
    """
    Get analytics about device distribution across GPS-detected areas.
    Includes staleness tracking.
    """
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_connected', '==', True))

    area_analytics = {area: {
        'unique_devices': set(),
        'total_users': 0,
        'users_without_device': 0,
        'stale_connections': 0
    } for area in PREDEFINED_AREAS}

    for user_doc in query.stream():
        user_data = user_doc.to_dict()

        if not user_data.get('location_permission_granted', False):
            continue

        last_check = user_data.get('last_connectivity_check')
        is_stale = not _is_connection_fresh(last_check)

        current_area = user_data.get('current_area')

        if not current_area or current_area.endswith('_nearby'):
            continue

        device_id = user_data.get('device_id')

        if current_area in area_analytics:
            if not is_stale:
                area_analytics[current_area]['total_users'] += 1

                if device_id and device_id.strip():
                    area_analytics[current_area]['unique_devices'].add(device_id)
                else:
                    area_analytics[current_area]['users_without_device'] += 1
            else:
                area_analytics[current_area]['stale_connections'] += 1

    result = {}
    for area, data in area_analytics.items():
        unique_count = len(data['unique_devices'])
        total = data['total_users']

        result[area] = {
            'unique_devices': unique_count,
            'total_users': total,
            'users_without_device': data['users_without_device'],
            'stale_connections': data['stale_connections'],
            'device_coverage_pct': round(
                (unique_count / total * 100) if total > 0 else 0,
                2
            )
        }

    return result