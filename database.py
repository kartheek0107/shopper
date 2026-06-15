"""
Database operations for the College Delivery System.

Production-hardened:
- All Firestore I/O is async (non-blocking event loop)
- Timezone-aware timestamps throughout
- Pagination support on list queries
- Firestore-side ordering instead of in-memory sort
"""

from datetime import timezone
from typing import List, Optional, Dict
from fastapi import HTTPException
import uuid
import logging

from firebase_admin import firestore as _fs
from google.cloud.firestore_v1 import Increment as _Increment
from firestore_async import (
    get_db, utcnow,
    get_doc, set_doc, update_doc,
    build_query, stream_query, stream_query_snapshots,
    run_transaction,
)
from reward_calculator import calculate_reward
from config import settings


# ============================================
# REQUEST OPERATIONS
# ============================================

async def create_request(user_uid: str, user_email: str, request_data: dict) -> dict:
    """
    Create a new request in Firestore with auto-calculated reward support.
    """
    if "item_price" not in request_data:
        raise HTTPException(status_code=400, detail="item_price is required for every request")

    request_id = str(uuid.uuid4())
    now = utcnow()

    item_price = request_data["item_price"]

    # AUTO-CALCULATE REWARD if not provided
    if "reward" not in request_data or request_data["reward"] is None:
        reward = calculate_reward(
            item_price=item_price,
            priority=request_data.get("priority", False),
            pickup_area=request_data.get("pickup_area"),
            drop_area=request_data.get("drop_area")
        )
        reward_auto_calculated = True
    else:
        reward = request_data["reward"]
        reward_auto_calculated = False

    # Get poster information
    user_data = await get_doc('users', user_uid)
    poster_name = 'Unknown'
    poster_phone = 'N/A'
    if user_data:
        poster_name = user_data.get('name', 'Unknown')
        poster_phone = user_data.get('phone', 'N/A')

    request_document = {
        "request_id": request_id,
        "posted_by": user_uid,
        "postedBy": user_uid,
        "poster_email": user_email,
        "posterEmail": user_email,
        "poster_name": poster_name,
        "posterName": poster_name,
        "poster_phone": poster_phone,
        "posterPhone": poster_phone,

        "item": request_data["item"],
        "pickup_location": request_data["pickup_location"],
        "pickupLocation": request_data["pickup_location"],
        "pickup_area": request_data.get("pickup_area"),
        "pickupArea": request_data.get("pickup_area"),
        "drop_location": request_data["drop_location"],
        "dropLocation": request_data["drop_location"],
        "drop_area": request_data.get("drop_area"),
        "dropArea": request_data.get("drop_area"),

        "item_price": request_data.get("item_price"),
        "itemPrice": request_data.get("item_price"),
        "reward": reward,
        "reward_auto_calculated": reward_auto_calculated,
        "rewardAutoCalculated": reward_auto_calculated,

        "time_requested": request_data.get("time_requested"),
        "timeRequested": request_data.get("time_requested"),

        "status": "open",
        "accepted_by": None, "acceptedBy": None,
        "acceptor_email": None, "acceptorEmail": None,
        "acceptor_name": None, "acceptorName": None,
        "acceptor_phone": None, "acceptorPhone": None,

        "created_at": now, "createdAt": now,
        "updated_at": now, "updatedAt": now,
        "accepted_at": None, "acceptedAt": None,
        "completed_at": None, "completedAt": None,

        "notes": request_data.get("notes"),
        "deadline": request_data.get("deadline"),
        "priority": request_data.get("priority", False),
        "is_expired": False, "isExpired": False,
    }

    await set_doc('requests', request_id, request_document)

    # Denormalize: increment poster's stats counters
    try:
        await update_doc('users', user_uid, {
            'stats.total_posted': _Increment(1),
            'stats.active_requests': _Increment(1),
        })
    except Exception as e:
        logging.getLogger(__name__).warning(f"Stats increment failed for {user_uid}: {e}")

    return request_document


async def create_request_with_gps(user_uid: str, user_email: str, request_data: dict) -> dict:
    """
    Create request with GPS support and auto-calculated reward.
    Auto-detect areas if GPS provided but areas not specified.
    """
    request_id = str(uuid.uuid4())
    now = utcnow()

    pickup_area = request_data.get("pickup_area")
    drop_area = request_data.get("drop_area")

    if not pickup_area and request_data.get("pickup_gps"):
        from location_service import detect_area_from_coordinates
        pickup_gps = request_data["pickup_gps"]
        pickup_area = detect_area_from_coordinates(
            pickup_gps["latitude"], pickup_gps["longitude"]
        )

    if not drop_area and request_data.get("drop_gps"):
        from location_service import detect_area_from_coordinates
        drop_gps = request_data["drop_gps"]
        drop_area = detect_area_from_coordinates(
            drop_gps["latitude"], drop_gps["longitude"]
        )

    delivery_distance = None
    if request_data.get("pickup_gps") and request_data.get("drop_gps"):
        from location_service import calculate_distance_meters
        pickup_gps = request_data["pickup_gps"]
        drop_gps = request_data["drop_gps"]
        delivery_distance = calculate_distance_meters(
            pickup_gps["latitude"], pickup_gps["longitude"],
            drop_gps["latitude"], drop_gps["longitude"]
        )

    item_price = request_data["item_price"]
    if "reward" not in request_data or request_data["reward"] is None:
        reward = calculate_reward(
            item_price=item_price,
            priority=request_data.get("priority", False),
            pickup_area=pickup_area,
            drop_area=drop_area
        )
        reward_auto_calculated = True
    else:
        reward = request_data["reward"]
        reward_auto_calculated = False

    user_data = await get_doc('users', user_uid)
    poster_name = 'Unknown'
    poster_phone = 'N/A'
    if user_data:
        poster_name = user_data.get('name', 'Unknown')
        poster_phone = user_data.get('phone', 'N/A')

    request_document = {
        "request_id": request_id,
        "posted_by": user_uid, "postedBy": user_uid,
        "poster_email": user_email, "posterEmail": user_email,
        "poster_name": poster_name, "posterName": poster_name,
        "poster_phone": poster_phone, "posterPhone": poster_phone,
        "item": request_data["item"],
        "pickup_location": request_data["pickup_location"],
        "pickupLocation": request_data["pickup_location"],
        "pickup_area": pickup_area, "pickupArea": pickup_area,
        "pickup_gps": request_data.get("pickup_gps"),
        "pickupGps": request_data.get("pickup_gps"),
        "drop_location": request_data["drop_location"],
        "dropLocation": request_data["drop_location"],
        "drop_area": drop_area, "dropArea": drop_area,
        "drop_gps": request_data.get("drop_gps"),
        "dropGps": request_data.get("drop_gps"),
        "delivery_distance_km": delivery_distance,
        "deliveryDistanceKm": delivery_distance,
        "time_requested": request_data.get("time_requested"),
        "timeRequested": request_data.get("time_requested"),
        "item_price": item_price, "itemPrice": item_price,
        "reward": reward,
        "reward_auto_calculated": reward_auto_calculated,
        "rewardAutoCalculated": reward_auto_calculated,
        "status": "open",
        "accepted_by": None, "acceptedBy": None,
        "acceptor_email": None, "acceptorEmail": None,
        "acceptor_name": None, "acceptorName": None,
        "acceptor_phone": None, "acceptorPhone": None,
        "created_at": now, "createdAt": now,
        "accepted_at": None, "acceptedAt": None,
        "completed_at": None, "completedAt": None,
        "updated_at": now, "updatedAt": now,
        "notes": request_data.get("notes"),
        "deadline": request_data.get("deadline"),
        "priority": request_data.get("priority", False),
        "is_expired": False, "isExpired": False,
    }

    await set_doc('requests', request_id, request_document)

    # Denormalize: increment poster's stats counters
    try:
        await update_doc('users', user_uid, {
            'stats.total_posted': _Increment(1),
            'stats.active_requests': _Increment(1),
        })
    except Exception as e:
        logging.getLogger(__name__).warning(f"Stats increment failed for {user_uid}: {e}")

    return request_document


async def mark_expired_requests() -> int:
    """
    Marks requests as expired if deadline passed and not completed.
    Returns count of newly expired requests.
    """
    now = utcnow()

    q = build_query(
        'requests',
        filters=[
            ('status', 'in', ['open', 'accepted']),
            ('is_expired', '==', False),
        ],
    )
    docs = await stream_query_snapshots(q)

    expired_count = 0
    for doc in docs:
        request_data = doc.to_dict()
        deadline = request_data.get('deadline')
        if not deadline:
            continue

        # Ensure deadline is timezone-aware
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        if deadline < now:
            await update_doc('requests', doc.id, {
                'is_expired': True,
                'status': 'cancelled',
                'updated_at': now,
                'cancelled_reason': 'Deadline expired',
            })
            expired_count += 1

    return expired_count


async def get_all_requests(
    status: Optional[str] = None,
    pickup_area: Optional[str] = None,
    drop_area: Optional[str] = None,
    include_expired: bool = False,
    limit: int = None,
) -> List[dict]:
    """
    Get requests with optional filters.
    Uses Firestore-side filtering where possible and pagination.
    """
    if limit is None:
        limit = settings.DEFAULT_PAGE_SIZE

    filters = []
    if status:
        filters.append(('status', '==', status))
    if not include_expired:
        filters.append(('is_expired', '==', False))

    # Firestore compound query — pickup_area / drop_area pushed to server
    # when possible (requires composite indexes; falls back to in-memory otherwise)
    if pickup_area and not drop_area:
        filters.append(('pickup_area', '==', pickup_area))
    elif drop_area and not pickup_area:
        filters.append(('drop_area', '==', drop_area))

    q = build_query(
        'requests',
        filters=filters if filters else None,
        order_by='created_at',
        descending=True,
        limit=limit,
    )
    requests = await stream_query(q)

    # If both pickup_area AND drop_area were requested, we can't push both
    # into a single Firestore inequality — filter the smaller set in memory
    if pickup_area and drop_area:
        requests = [
            r for r in requests
            if r.get('pickup_area') == pickup_area
            and r.get('drop_area') == drop_area
        ]

    # If only drop_area was used as the server filter and pickup_area was also
    # supplied, the pickup filter was already pushed.  Vice-versa handled above.

    return requests


async def get_user_requests(user_uid: str, limit: int = None) -> List[dict]:
    """Get all requests posted by a specific user."""
    if limit is None:
        limit = settings.MAX_PAGE_SIZE

    q = build_query(
        'requests',
        filters=[('posted_by', '==', user_uid)],
        order_by='created_at',
        descending=True,
        limit=limit,
    )
    return await stream_query(q)


async def get_accepted_requests(user_uid: str, limit: int = None) -> List[dict]:
    """Get all requests accepted by a specific user."""
    if limit is None:
        limit = settings.MAX_PAGE_SIZE

    q = build_query(
        'requests',
        filters=[('accepted_by', '==', user_uid)],
        order_by='created_at',
        descending=True,
        limit=limit,
    )
    return await stream_query(q)


async def get_request_by_id(request_id: str) -> Optional[dict]:
    """Get a specific request by ID."""
    return await get_doc('requests', request_id)


async def accept_request(request_id: str, user_uid: str, user_email: str) -> dict:
    """
    Accept a request (atomic transaction to prevent double-accept).
    """
    db = get_db()
    request_ref = db.collection('requests').document(request_id)

    # Get acceptor info BEFORE the transaction (reads inside transactions
    # count toward the 500-write limit, so minimise them)
    acceptor_data = await get_doc('users', user_uid)
    acceptor_name = 'Unknown'
    acceptor_phone = 'N/A'
    if acceptor_data:
        acceptor_name = acceptor_data.get('name', 'Unknown')
        acceptor_phone = acceptor_data.get('phone', 'N/A')

    @_fs.transactional
    def _accept_txn(transaction, ref, uid, email, a_name, a_phone):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            raise HTTPException(status_code=404, detail="Request not found")

        data = snapshot.to_dict()

        if data['status'] != 'open':
            raise HTTPException(
                status_code=400,
                detail=f"Request is already {data['status']}"
            )
        if data['posted_by'] == uid:
            raise HTTPException(
                status_code=400,
                detail="You cannot accept your own request"
            )

        now = utcnow()
        updates = {
            'status': 'accepted',
            'accepted_by': uid, 'acceptedBy': uid,
            'acceptor_email': email, 'acceptorEmail': email,
            'acceptor_name': a_name, 'acceptorName': a_name,
            'acceptor_phone': a_phone, 'acceptorPhone': a_phone,
            'accepted_at': now, 'acceptedAt': now,
            'updated_at': now, 'updatedAt': now,
        }
        transaction.update(ref, updates)
        data.update(updates)
        return data

    result = await run_transaction(
        _accept_txn,
        ref=request_ref,
        uid=user_uid,
        email=user_email,
        a_name=acceptor_name,
        a_phone=acceptor_phone,
    )

    # Denormalize: increment acceptor's stats counters
    try:
        await update_doc('users', user_uid, {
            'stats.total_accepted': _Increment(1),
        })
    except Exception as e:
        logging.getLogger(__name__).warning(f"Stats increment failed for {user_uid}: {e}")

    return result


async def update_request_status(
    request_id: str,
    new_status: str,
    user_uid: str
) -> dict:
    """Update request status (only by poster or acceptor)."""
    request_data = await get_doc('requests', request_id)
    if request_data is None:
        raise HTTPException(status_code=404, detail="Request not found")

    is_poster = request_data['posted_by'] == user_uid
    is_acceptor = request_data.get('accepted_by') == user_uid
    if not (is_poster or is_acceptor):
        raise HTTPException(status_code=403, detail="Not authorized to update this request")

    current_status = request_data['status']
    valid_transitions = {
        'open': ['accepted', 'cancelled'],
        'accepted': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': [],
    }
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current_status} to {new_status}"
        )

    now = utcnow()
    update_data = {'status': new_status, 'updated_at': now}
    if new_status == 'completed':
        update_data['completed_at'] = now

    await update_doc('requests', request_id, update_data)
    request_data.update(update_data)

    # Denormalize: update stats counters based on transition
    _log = logging.getLogger(__name__)
    try:
        poster_uid = request_data['posted_by']
        acceptor_uid = request_data.get('accepted_by')

        if new_status == 'completed' and acceptor_uid:
            await update_doc('users', acceptor_uid, {
                'stats.total_completed': _Increment(1),
            })
            # Decrement active_requests on poster
            await update_doc('users', poster_uid, {
                'stats.active_requests': _Increment(-1),
            })
        elif new_status == 'cancelled' and current_status == 'open':
            # Request was open and is now cancelled — decrement active_requests
            await update_doc('users', poster_uid, {
                'stats.active_requests': _Increment(-1),
            })
    except Exception as e:
        _log.warning(f"Stats decrement failed for request {request_id}: {e}")

    return request_data


# ============================================
# USER OPERATIONS
# ============================================

async def get_user_profile(user_uid: str) -> Optional[dict]:
    """Get user profile from Firestore."""
    return await get_doc('users', user_uid)


async def update_user_profile(user_uid: str, profile_data: dict) -> dict:
    """Update user profile."""
    update_data = {**profile_data, 'updated_at': utcnow()}
    await update_doc('users', user_uid, update_data)
    return await get_doc('users', user_uid)


async def get_user_stats(user_uid: str) -> dict:
    """
    Get user statistics (requests posted, accepted, completed).

    First tries the denormalized ``stats`` field on the user document
    (single read).  Falls back to the legacy 4-query approach for
    users whose stats haven't been initialized yet.
    """
    user_data = await get_doc('users', user_uid)
    if user_data and 'stats' in user_data:
        stats = user_data['stats']
        return {
            'total_posted': stats.get('total_posted', 0),
            'total_accepted': stats.get('total_accepted', 0),
            'total_completed': stats.get('total_completed', 0),
            'active_requests': max(stats.get('active_requests', 0), 0),
        }

    # Legacy fallback — runs 4 queries (will be used only for old users)
    import asyncio
    posted_q = stream_query(
        build_query('requests', filters=[('posted_by', '==', user_uid)])
    )
    accepted_q = stream_query(
        build_query('requests', filters=[('accepted_by', '==', user_uid)])
    )
    completed_q = stream_query(
        build_query('requests', filters=[
            ('accepted_by', '==', user_uid),
            ('status', '==', 'completed'),
        ])
    )
    active_q = stream_query(
        build_query('requests', filters=[
            ('posted_by', '==', user_uid),
            ('status', '==', 'open'),
        ])
    )

    posted, accepted, completed, active = await asyncio.gather(
        posted_q, accepted_q, completed_q, active_q
    )

    stats = {
        'total_posted': len(posted),
        'total_accepted': len(accepted),
        'total_completed': len(completed),
        'active_requests': len(active),
    }

    # Seed the stats field so future reads are fast
    try:
        await update_doc('users', user_uid, {'stats': stats})
    except Exception:
        pass

    return stats