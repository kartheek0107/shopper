from firebase_admin import firestore
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import HTTPException
import uuid

# Get Firestore client
db = firestore.client()


# ============================================
# REQUEST OPERATIONS
# ============================================

async def create_request(user_uid: str, user_email: str, request_data: dict) -> dict:
    """
    Create a new request in Firestore
    
    Args:
        user_uid: UID of the user creating the request
        user_email: Email of the user creating the request
        request_data: Request details
        
    Returns:
        dict: Created request with request_id
    """
    request_id = str(uuid.uuid4())
    
    request_document = {
        "request_id": request_id,
        "posted_by": user_uid,
        "poster_email": user_email,
        "item": request_data["item"],
        "pickup_location": request_data["pickup_location"],
        "drop_location": request_data["drop_location"],
        "time_requested": request_data["time_requested"],
        "reward": request_data["reward"],
        "status": "open",
        "accepted_by": None,
        "acceptor_email": None,
        "created_at": datetime.utcnow(),
        "notes": request_data.get("notes")
    }
    
    # Store in Firestore
    db.collection('requests').document(request_id).set(request_document)
    
    return request_document


async def get_all_requests(status: Optional[str] = None) -> List[dict]:
    """
    Get all requests, optionally filtered by status
    
    Args:
        status: Optional status filter (open, accepted, completed)
        
    Returns:
        List[dict]: List of requests
    """
    requests_ref = db.collection('requests')
    
    if status:
        # Use the new filter syntax
        query = requests_ref.where(filter=firestore.FieldFilter('status', '==', status))
    else:
        query = requests_ref
    
    # Order by creation time (newest first)
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    
    requests = []
    for doc in query.stream():
        request_data = doc.to_dict()
        requests.append(request_data)
    
    return requests


async def get_user_requests(user_uid: str) -> List[dict]:
    """
    Get all requests posted by a specific user
    
    Args:
        user_uid: UID of the user
        
    Returns:
        List[dict]: List of user's requests
    """
    requests_ref = db.collection('requests')
    query = requests_ref.where(filter=firestore.FieldFilter('posted_by', '==', user_uid))
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    
    requests = []
    for doc in query.stream():
        request_data = doc.to_dict()
        requests.append(request_data)
    
    return requests


async def get_accepted_requests(user_uid: str) -> List[dict]:
    """
    Get all requests accepted by a specific user
    
    Args:
        user_uid: UID of the user
        
    Returns:
        List[dict]: List of accepted requests
    """
    requests_ref = db.collection('requests')
    query = requests_ref.where(filter=firestore.FieldFilter('accepted_by', '==', user_uid))
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
    
    requests = []
    for doc in query.stream():
        request_data = doc.to_dict()
        requests.append(request_data)
    
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
        return doc.to_dict()
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
        
        # Update request
        transaction.update(request_ref, {
            'status': 'accepted',
            'accepted_by': user_uid,
            'acceptor_email': user_email,
            'accepted_at': datetime.utcnow()
        })
        
        # Return updated data
        request_data.update({
            'status': 'accepted',
            'accepted_by': user_uid,
            'acceptor_email': user_email
        })
        return request_data
    
    # Execute transaction
    transaction = db.transaction()
    updated_request = update_in_transaction(transaction)
    
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
    update_data = {
        'status': new_status,
        'updated_at': datetime.utcnow()
    }
    
    if new_status == 'completed':
        update_data['completed_at'] = datetime.utcnow()
    
    request_ref.update(update_data)
    request_data.update(update_data)
    
    return request_data


# ============================================
# USER OPERATIONS
# ============================================

async def update_user_reachability(user_uid: str, reachable: bool) -> dict:
    """
    Update user's reachability status
    
    Args:
        user_uid: User UID
        reachable: Whether user is available for deliveries
        
    Returns:
        dict: Updated user data
    """
    user_ref = db.collection('users').document(user_uid)
    
    user_ref.update({
        'reachable': reachable,
        'updated_at': datetime.utcnow()
    })
    
    user_doc = user_ref.get()
    return user_doc.to_dict()


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
        'updated_at': datetime.utcnow()
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
    completed_query = requests_ref.where(filter=firestore.FieldFilter('accepted_by', '==', user_uid)).where(filter=firestore.FieldFilter('status', '==', 'completed'))
    total_completed = len(list(completed_query.stream()))
    
    # Count active requests (posted and still open)
    active_query = requests_ref.where(filter=firestore.FieldFilter('posted_by', '==', user_uid)).where(filter=firestore.FieldFilter('status', '==', 'open'))
    active_requests = len(list(active_query.stream()))
    
    return {
        'total_posted': total_posted,
        'total_accepted': total_accepted,
        'total_completed': total_completed,
        'active_requests': active_requests
    }