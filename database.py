from firebase_admin import firestore
from datetime import datetime, timezone
from typing import List, Optional, Dict
from fastapi import HTTPException
import uuid

# Import reward calculator
from reward_calculator import calculate_reward

# Get Firestore client
db = firestore.client()


# ============================================
# REQUEST OPERATIONS (Updated for Auto Reward + GPS)
# ============================================

async def create_request(user_uid: str, user_email: str, request_data: dict) -> dict:
    """
    Create a new request in Firestore with auto-calculated reward support.

    Changes:
    - reward is now OPTIONAL - auto-calculated if not provided
    - time_requested is now OPTIONAL - no longer required
    - Adds reward_auto_calculated field to track calculation source
    """

    # Validate required field: item_price
    if "item_price" not in request_data:
        raise HTTPException(status_code=400, detail="item_price is required for every request")

    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

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
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()
    poster_name = 'Unknown'
    poster_phone = 'N/A'

    if user_doc.exists:
        user_data = user_doc.to_dict()
        poster_name = user_data.get('name', 'Unknown')
        poster_phone = user_data.get('phone', 'N/A')

    request_document = {
        "request_id": request_id,
        "posted_by": user_uid,
        "postedBy": user_uid,  # camelCase version
        "poster_email": user_email,
        "posterEmail": user_email,  # camelCase version
        "poster_name": poster_name,
        "posterName": poster_name,  # camelCase version
        "poster_phone": poster_phone,
        "posterPhone": poster_phone,  # camelCase version

        "item": request_data["item"],
        "pickup_location": request_data["pickup_location"],
        "pickupLocation": request_data["pickup_location"],  # camelCase version
        "pickup_area": request_data.get("pickup_area"),
        "pickupArea": request_data.get("pickup_area"),  # camelCase version
        "drop_location": request_data["drop_location"],
        "dropLocation": request_data["drop_location"],  # camelCase version
        "drop_area": request_data.get("drop_area"),
        "dropArea": request_data.get("drop_area"),  # camelCase version

        # Item price (required)
        "item_price": request_data.get("item_price"),
        "itemPrice": request_data.get("item_price"),  # camelCase version

        # Reward (auto-calculated or user-provided)
        "reward": reward,
        "reward_auto_calculated": reward_auto_calculated,
        "rewardAutoCalculated": reward_auto_calculated,  # camelCase version

        # Time requested (now optional)
        "time_requested": request_data.get("time_requested"),
        "timeRequested": request_data.get("time_requested"),  # camelCase version

        "status": "open",
        "accepted_by": None,
        "acceptedBy": None,  # camelCase version
        "acceptor_email": None,
        "acceptorEmail": None,  # camelCase version
        "acceptor_name": None,
        "acceptorName": None,  # camelCase version
        "acceptor_phone": None,
        "acceptorPhone": None,  # camelCase version

        # Timestamps
        "created_at": now,
        "createdAt": now,  # camelCase version
        "updated_at": now,
        "updatedAt": now,  # camelCase version
        "accepted_at": None,
        "acceptedAt": None,  # camelCase version
        "completed_at": None,
        "completedAt": None,  # camelCase version

        "notes": request_data.get("notes"),
        "deadline": request_data.get("deadline"),
        "priority": request_data.get("priority", False),
        "is_expired": False,
        "isExpired": False,  # camelCase version
    }

    db.collection('requests').document(request_id).set(request_document)
    return request_document


async def create_request_with_gps(user_uid: str, user_email: str, request_data: dict) -> dict:
    """
    Create request with GPS support and auto-calculated reward
    Auto-detect areas if GPS provided but areas not specified
    """
    request_id = str(uuid.uuid4())

    # Auto-detect areas from GPS if not provided
    pickup_area = request_data.get("pickup_area")
    drop_area = request_data.get("drop_area")

    if not pickup_area and request_data.get("pickup_gps"):
        from location_service import detect_area_from_coordinates
        pickup_gps = request_data["pickup_gps"]
        pickup_area = detect_area_from_coordinates(
            pickup_gps["latitude"],
            pickup_gps["longitude"]
        )

    if not drop_area and request_data.get("drop_gps"):
        from location_service import detect_area_from_coordinates
        drop_gps = request_data["drop_gps"]
        drop_area = detect_area_from_coordinates(
            drop_gps["latitude"],
            drop_gps["longitude"]
        )

    # Calculate delivery distance if both GPS coordinates provided
    delivery_distance = None
    if request_data.get("pickup_gps") and request_data.get("drop_gps"):
        from location_service import calculate_distance
        pickup_gps = request_data["pickup_gps"]
        drop_gps = request_data["drop_gps"]
        delivery_distance = calculate_distance(
            pickup_gps["latitude"], pickup_gps["longitude"],
            drop_gps["latitude"], drop_gps["longitude"]
        )

    # AUTO-CALCULATE REWARD if not provided (AFTER area detection)
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

    # Get poster information
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()
    poster_name = 'Unknown'
    poster_phone = 'N/A'

    if user_doc.exists:
        user_data = user_doc.to_dict()
        poster_name = user_data.get('name', 'Unknown')
        poster_phone = user_data.get('phone', 'N/A')

    request_document = {
        "request_id": request_id,
        "posted_by": user_uid,
        "postedBy": user_uid,  # camelCase
        "poster_email": user_email,
        "posterEmail": user_email,  # camelCase
        "poster_name": poster_name,
        "posterName": poster_name,  # camelCase
        "poster_phone": poster_phone,
        "posterPhone": poster_phone,  # camelCase
        "item": request_data["item"],
        "pickup_location": request_data["pickup_location"],
        "pickupLocation": request_data["pickup_location"],  # camelCase
        "pickup_area": pickup_area,
        "pickupArea": pickup_area,  # camelCase
        "pickup_gps": request_data.get("pickup_gps"),
        "pickupGps": request_data.get("pickup_gps"),  # camelCase
        "drop_location": request_data["drop_location"],
        "dropLocation": request_data["drop_location"],  # camelCase
        "drop_area": drop_area,
        "dropArea": drop_area,  # camelCase
        "drop_gps": request_data.get("drop_gps"),
        "dropGps": request_data.get("drop_gps"),  # camelCase
        "delivery_distance_km": delivery_distance,
        "deliveryDistanceKm": delivery_distance,  # camelCase

        # Time requested (now optional)
        "time_requested": request_data.get("time_requested"),
        "timeRequested": request_data.get("time_requested"),  # camelCase

        # Item price and reward
        "item_price": item_price,
        "itemPrice": item_price,  # camelCase
        "reward": reward,
        "reward_auto_calculated": reward_auto_calculated,
        "rewardAutoCalculated": reward_auto_calculated,  # camelCase

        "status": "open",
        "accepted_by": None,
        "acceptedBy": None,  # camelCase
        "acceptor_email": None,
        "acceptorEmail": None,  # camelCase
        "acceptor_name": None,
        "acceptorName": None,  # camelCase
        "acceptor_phone": None,
        "acceptorPhone": None,  # camelCase
        "created_at": datetime.now(timezone.utc),
        "createdAt": datetime.now(timezone.utc),  # camelCase
        "accepted_at": None,
        "acceptedAt": None,  # camelCase
        "completed_at": None,
        "completedAt": None,  # camelCase
        "updated_at": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),  # camelCase
        "notes": request_data.get("notes"),
        "deadline": request_data.get("deadline"),
        "priority": request_data.get("priority", False),
        "is_expired": False,
        "isExpired": False,  # camelCase
    }

    # Store in Firestore
    db.collection('requests').document(request_id).set(request_document)

    return request_document


async def mark_expired_requests() -> int:
    """
    Marks requests as expired if deadline passed and not completed.

    Returns:
        int: Number of requests marked as expired
    """
    requests_ref = db.collection('requests')

    # Get all open/accepted requests
    query = requests_ref.where(
        filter=firestore.FieldFilter('status', 'in', ['open', 'accepted'])
    ).where(
        filter=firestore.FieldFilter('is_expired', '==', False)
    )

    now = datetime.now(timezone.utc)
    expired_count = 0

    for doc in query.stream():
        request_data = doc.to_dict()
        deadline = request_data.get('deadline')

        if deadline:
            # Ensure deadline is timezone-aware
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)

            if deadline < now:
                # Mark as expired and cancelled
                doc.reference.update({
                    'is_expired': True,
                    'status': 'cancelled',
                    'updated_at': now,
                    'cancelled_reason': 'Deadline expired'
                })
                expired_count += 1

    return expired_count


def enrich_request_with_poster_info(request_data: dict) -> dict:
    """
    Enrich request data with poster information from user document

    Args:
        request_data: Request data dict

    Returns:
        dict: Request data enriched with posterName and posterPhone (camelCase)
    """
    # Check both snake_case and camelCase
    has_snake_case = 'poster_name' in request_data and 'poster_phone' in request_data
    has_camel_case = 'posterName' in request_data and 'posterPhone' in request_data

    if has_snake_case or has_camel_case:
        # If has snake_case but not camelCase, convert
        if has_snake_case and not has_camel_case:
            request_data['posterName'] = request_data.get('poster_name', 'Unknown')
            request_data['posterPhone'] = request_data.get('poster_phone', 'N/A')
        return request_data

    # Get poster information
    poster_uid = request_data.get('posted_by') or request_data.get('postedBy')
    if poster_uid:
        user_ref = db.collection('users').document(poster_uid)
        user_doc = user_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            poster_name = user_data.get('name', 'Unknown')
            poster_phone = user_data.get('phone', 'N/A')
        else:
            poster_name = 'Unknown'
            poster_phone = 'N/A'
    else:
        poster_name = 'Unknown'
        poster_phone = 'N/A'

    # Set both formats to ensure compatibility
    request_data['poster_name'] = poster_name
    request_data['poster_phone'] = poster_phone
    request_data['posterName'] = poster_name
    request_data['posterPhone'] = poster_phone

    return request_data


def enrich_request_with_acceptor_info(request_data: dict) -> dict:
    """
    Enrich request data with acceptor information from user document

    Args:
        request_data: Request data dict

    Returns:
        dict: Request data enriched with acceptorName and acceptorPhone (camelCase)
    """
    # Check both snake_case and camelCase
    has_snake_case = 'acceptor_name' in request_data and 'acceptor_phone' in request_data
    has_camel_case = 'acceptorName' in request_data and 'acceptorPhone' in request_data

    if has_snake_case or has_camel_case:
        # If has snake_case but not camelCase, convert
        if has_snake_case and not has_camel_case:
            request_data['acceptorName'] = request_data.get('acceptor_name', 'Unknown')
            request_data['acceptorPhone'] = request_data.get('acceptor_phone', 'N/A')
        return request_data

    # Get acceptor information
    acceptor_uid = request_data.get('accepted_by') or request_data.get('acceptedBy')

    if acceptor_uid:
        user_ref = db.collection('users').document(acceptor_uid)
        user_doc = user_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            acceptor_name = user_data.get('name', 'Unknown')
            acceptor_phone = user_data.get('phone', 'N/A')
        else:
            acceptor_name = 'Unknown'
            acceptor_phone = 'N/A'
    else:
        # No acceptor yet (request still open)
        acceptor_name = None
        acceptor_phone = None

    # Set both formats to ensure compatibility
    request_data['acceptor_name'] = acceptor_name
    request_data['acceptor_phone'] = acceptor_phone
    request_data['acceptorName'] = acceptor_name
    request_data['acceptorPhone'] = acceptor_phone

    return request_data


async def get_all_requests(
        status: Optional[str] = None,
        pickup_area: Optional[str] = None,
        drop_area: Optional[str] = None,
        include_expired: bool = False
) -> List[dict]:
    """
    Get all requests with optional filters

    Args:
        status: Optional status filter
        pickup_area: Optional pickup area filter
        drop_area: Optional drop area filter
        include_expired: Whether to include expired requests

    Returns:
        List[dict]: List of requests
    """
    requests_ref = db.collection('requests')

    # Start with status filter if provided
    if status:
        query = requests_ref.where(filter=firestore.FieldFilter('status', '==', status))
    else:
        query = requests_ref

    # Get all matching documents
    requests = []
    for doc in query.stream():
        request_data = doc.to_dict()

        # Apply area filters in memory
        if pickup_area and request_data.get('pickup_area') != pickup_area:
            continue
        if drop_area and request_data.get('drop_area') != drop_area:
            continue
        if not include_expired and request_data.get('is_expired', False):
            continue

        # Enrich with poster information
        request_data = enrich_request_with_poster_info(request_data)
        # Enrich with acceptor information
        request_data = enrich_request_with_acceptor_info(request_data)

        requests.append(request_data)

    # Sort by creation time (newest first)
    requests.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)

    return requests


async def get_user_requests(user_uid: str) -> List[dict]:
    """
    Get all requests posted by a specific user

    ✅ FIXED: Removed .order_by() to avoid Firestore composite index requirement
    Now sorts in Python instead
    ✅ FIXED: Added poster information enrichment

    Args:
        user_uid: UID of the user

    Returns:
        List[dict]: List of user's requests
    """
    requests_ref = db.collection('requests')
    query = requests_ref.where(filter=firestore.FieldFilter('posted_by', '==', user_uid))

    requests = []
    for doc in query.stream():
        request_data = doc.to_dict()

        # Enrich with poster information
        request_data = enrich_request_with_poster_info(request_data)
        # Enrich with acceptor information
        request_data = enrich_request_with_acceptor_info(request_data)

        requests.append(request_data)

    # ✅ FIX: Sort in Python instead (no index required)
    requests.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)

    return requests


async def get_accepted_requests(user_uid: str) -> List[dict]:
    """
    Get all requests accepted by a specific user

    ✅ FIXED: Removed .order_by() to avoid Firestore composite index requirement
    Now sorts in Python instead
    ✅ FIXED: Added poster information enrichment

    Args:
        user_uid: UID of the user

    Returns:
        List[dict]: List of accepted requests
    """
    requests_ref = db.collection('requests')
    query = requests_ref.where(filter=firestore.FieldFilter('accepted_by', '==', user_uid))

    requests = []
    for doc in query.stream():
        request_data = doc.to_dict()

        # Enrich with poster information
        request_data = enrich_request_with_poster_info(request_data)
        # Enrich with acceptor information
        request_data = enrich_request_with_acceptor_info(request_data)

        requests.append(request_data)

    # ✅ FIX: Sort in Python instead (no index required)
    requests.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)

    return requests


async def get_request_by_id(request_id: str) -> Optional[dict]:
    """
    Get a specific request by ID

    Args:
        request_id: Request ID

    Returns:
        dict: Request data or None if not found
    """
    doc = db.collection('requests').document(request_id).get()

    if doc.exists:
        request_data = doc.to_dict()
        # Enrich with poster information
        request_data = enrich_request_with_poster_info(request_data)
        # Enrich with acceptor information
        request_data = enrich_request_with_acceptor_info(request_data)
        return request_data
    return None


async def accept_request(request_id: str, user_uid: str, user_email: str) -> dict:
    """
    Accept a request (atomic operation)

    Args:
        request_id: Request ID to accept
        user_uid: UID of the user accepting
        user_email: Email of the user accepting

    Returns:
        dict: Updated request data

    Raises:
        HTTPException: If request not found, already accepted, or user is the poster
    """
    request_ref = db.collection('requests').document(request_id)

    # Use transaction for atomic update
    @firestore.transactional
    def update_in_transaction(transaction):
        snapshot = request_ref.get(transaction=transaction)

        if not snapshot.exists:
            raise HTTPException(status_code=404, detail="Request not found")

        request_data = snapshot.to_dict()

        # Check if already accepted
        if request_data['status'] != 'open':
            raise HTTPException(
                status_code=400,
                detail=f"Request is already {request_data['status']}"
            )

        # Check if user is trying to accept their own request
        if request_data['posted_by'] == user_uid:
            raise HTTPException(
                status_code=400,
                detail="You cannot accept your own request"
            )

        # Get acceptor's name and phone from Firestore
        user_ref = db.collection('users').document(user_uid)
        user_doc = user_ref.get()
        acceptor_name = 'Unknown'
        acceptor_phone = 'N/A'

        if user_doc.exists:
            user_data = user_doc.to_dict()
            acceptor_name = user_data.get('name', 'Unknown')
            acceptor_phone = user_data.get('phone', 'N/A')

        # Update request
        now = datetime.now(timezone.utc)
        transaction.update(request_ref, {
            'status': 'accepted',
            'accepted_by': user_uid,
            'acceptedBy': user_uid,  # camelCase
            'acceptor_email': user_email,
            'acceptorEmail': user_email,  # camelCase
            'acceptor_name': acceptor_name,
            'acceptorName': acceptor_name,  # camelCase
            'acceptor_phone': acceptor_phone,
            'acceptorPhone': acceptor_phone,  # camelCase
            'accepted_at': now,
            'acceptedAt': now,  # camelCase
            'updated_at': now,
            'updatedAt': now  # camelCase
        })

        # Return updated data
        request_data.update({
            'status': 'accepted',
            'accepted_by': user_uid,
            'acceptedBy': user_uid,
            'acceptor_email': user_email,
            'acceptorEmail': user_email,
            'acceptor_name': acceptor_name,
            'acceptorName': acceptor_name,
            'acceptor_phone': acceptor_phone,
            'acceptorPhone': acceptor_phone,
            'accepted_at': now,
            'acceptedAt': now,
            'updated_at': now,
            'updatedAt': now
        })
        return request_data

    # Execute transaction
    transaction = db.transaction()
    updated_request = update_in_transaction(transaction)

    # Enrich with poster information
    updated_request = enrich_request_with_poster_info(updated_request)

    return updated_request


async def update_request_status(
        request_id: str,
        new_status: str,
        user_uid: str
) -> dict:
    """
    Update request status (only by poster or acceptor)

    Args:
        request_id: Request ID
        new_status: New status (accepted, completed, cancelled)
        user_uid: UID of user making the update

    Returns:
        dict: Updated request data

    Raises:
        HTTPException: If not authorized or invalid status transition
    """
    request_ref = db.collection('requests').document(request_id)
    doc = request_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Request not found")

    request_data = doc.to_dict()

    # Authorization check
    is_poster = request_data['posted_by'] == user_uid
    is_acceptor = request_data.get('accepted_by') == user_uid

    if not (is_poster or is_acceptor):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to update this request"
        )

    # Validate status transition
    current_status = request_data['status']
    valid_transitions = {
        'open': ['accepted', 'cancelled'],
        'accepted': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': []
    }

    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current_status} to {new_status}"
        )

    # Update status
    now = datetime.now(timezone.utc)
    update_data = {
        'status': new_status,
        'updated_at': now
    }

    if new_status == 'completed':
        update_data['completed_at'] = now

    request_ref.update(update_data)
    request_data.update(update_data)

    # Enrich with poster information
    request_data = enrich_request_with_poster_info(request_data)
    # Enrich with acceptor information
    request_data = enrich_request_with_acceptor_info(request_data)

    return request_data


# ============================================
# USER OPERATIONS (Enhanced for Phase 3)
# ============================================

async def get_user_profile(user_uid: str) -> Optional[dict]:
    """
    Get user profile from Firestore

    Args:
        user_uid: User UID

    Returns:
        dict: User data or None if not found
    """
    user_doc = db.collection('users').document(user_uid).get()

    if user_doc.exists:
        return user_doc.to_dict()
    return None


async def update_user_profile(user_uid: str, profile_data: dict) -> dict:
    """
    Update user profile

    Args:
        user_uid: User UID
        profile_data: Profile fields to update

    Returns:
        dict: Updated user data
    """
    user_ref = db.collection('users').document(user_uid)

    update_data = {
        **profile_data,
        'updated_at': datetime.now(timezone.utc)
    }

    user_ref.update(update_data)

    user_doc = user_ref.get()
    return user_doc.to_dict()


async def get_user_stats(user_uid: str) -> dict:
    """
    Get user statistics (requests posted, accepted, completed)

    Args:
        user_uid: User UID

    Returns:
        dict: User statistics
    """
    requests_ref = db.collection('requests')

    # Count posted requests
    posted_query = requests_ref.where(filter=firestore.FieldFilter('posted_by', '==', user_uid))
    total_posted = len(list(posted_query.stream()))

    # Count accepted requests
    accepted_query = requests_ref.where(filter=firestore.FieldFilter('accepted_by', '==', user_uid))
    total_accepted = len(list(accepted_query.stream()))

    # Count completed requests (as acceptor)
    completed_query = requests_ref.where(filter=firestore.FieldFilter('accepted_by', '==', user_uid)).where(
        filter=firestore.FieldFilter('status', '==', 'completed'))
    total_completed = len(list(completed_query.stream()))

    # Count active requests (posted and still open)
    active_query = requests_ref.where(filter=firestore.FieldFilter('posted_by', '==', user_uid)).where(
        filter=firestore.FieldFilter('status', '==', 'open'))
    active_requests = len(list(active_query.stream()))

    return {
        'total_posted': total_posted,
        'total_accepted': total_accepted,
        'total_completed': total_completed,
        'active_requests': active_requests
    }