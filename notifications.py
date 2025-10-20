"""
Push Notifications System using Firebase Cloud Messaging (FCM)
Handles notification sending for request events
"""

from typing import Optional, Dict, List
from firebase_admin import messaging, firestore
from datetime import datetime
from fastapi import HTTPException
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Firestore client
db = firestore.client()


async def register_fcm_token(user_uid: str, fcm_token: str) -> Dict:
    """
    Register or update FCM token for a user
    
    Args:
        user_uid: User UID
        fcm_token: Firebase Cloud Messaging token
        
    Returns:
        dict: Success response
    """
    user_ref = db.collection('users').document(user_uid)
    
    user_ref.update({
        'fcm_token': fcm_token,
        'fcm_token_updated_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    })
    
    logger.info(f"FCM token registered for user {user_uid}")
    
    return {
        'success': True,
        'message': 'FCM token registered successfully'
    }


async def get_user_fcm_token(user_uid: str) -> Optional[str]:
    """
    Get FCM token for a user
    
    Args:
        user_uid: User UID
        
    Returns:
        str: FCM token or None if not found
    """
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return None
    
    user_data = user_doc.to_dict()
    return user_data.get('fcm_token')


async def send_notification(
    user_uid: str,
    title: str,
    body: str,
    data: Optional[Dict] = None
) -> bool:
    """
    Send push notification to a user
    
    Args:
        user_uid: User UID to send notification to
        title: Notification title
        body: Notification body
        data: Optional additional data payload
        
    Returns:
        bool: True if sent successfully
    """
    fcm_token = await get_user_fcm_token(user_uid)
    
    if not fcm_token:
        logger.warning(f"No FCM token found for user {user_uid}")
        return False
    
    try:
        # Create notification message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data or {},
            token=fcm_token
        )
        
        # Send message
        response = messaging.send(message)
        logger.info(f"Notification sent to {user_uid}: {response}")
        
        return True
        
    except messaging.UnregisteredError:
        logger.warning(f"FCM token invalid for user {user_uid}, removing token")
        # Remove invalid token
        user_ref = db.collection('users').document(user_uid)
        user_ref.update({'fcm_token': firestore.DELETE_FIELD})
        return False
        
    except Exception as e:
        logger.error(f"Error sending notification to {user_uid}: {str(e)}")
        return False


async def send_request_accepted_notification(
    poster_uid: str,
    acceptor_email: str,
    item: str,
    request_id: str
) -> bool:
    """
    Notify poster that their request was accepted
    
    Args:
        poster_uid: UID of request poster
        acceptor_email: Email of person who accepted
        item: Item name
        request_id: Request ID
        
    Returns:
        bool: True if sent successfully
    """
    title = "Request Accepted! 🎉"
    body = f"{acceptor_email} accepted your request for '{item}'"
    
    data = {
        'type': 'request_accepted',
        'request_id': request_id,
        'acceptor_email': acceptor_email
    }
    
    return await send_notification(poster_uid, title, body, data)


async def send_delivery_completed_notification(
    poster_uid: str,
    deliverer_email: str,
    item: str,
    request_id: str
) -> bool:
    """
    Notify poster that delivery is completed
    
    Args:
        poster_uid: UID of request poster
        deliverer_email: Email of deliverer
        item: Item name
        request_id: Request ID
        
    Returns:
        bool: True if sent successfully
    """
    title = "Delivery Completed! ✅"
    body = f"{deliverer_email} completed delivery of '{item}'"
    
    data = {
        'type': 'delivery_completed',
        'request_id': request_id,
        'deliverer_email': deliverer_email
    }
    
    return await send_notification(poster_uid, title, body, data)


async def send_new_request_in_area_notification(
    area: str,
    item: str,
    request_id: str,
    exclude_uid: str
) -> int:
    """
    Notify users with preferred areas about new request
    
    Args:
        area: Area where request is posted
        item: Item name
        request_id: Request ID
        exclude_uid: UID to exclude (poster)
        
    Returns:
        int: Number of notifications sent
    """
    # Get all reachable users with this area in preferences
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_reachable', '==', True))
    
    title = f"New Request in {area}! 📦"
    body = f"Someone needs '{item}' delivered"
    
    data = {
        'type': 'new_request',
        'request_id': request_id,
        'area': area
    }
    
    sent_count = 0
    
    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        user_uid = user_data.get('uid')
        
        # Skip poster
        if user_uid == exclude_uid:
            continue
        
        # Check if user has this area in preferences
        preferred_areas = user_data.get('preferred_areas', [])
        if area not in preferred_areas:
            continue
        
        # Send notification
        if await send_notification(user_uid, title, body, data):
            sent_count += 1
    
    logger.info(f"Sent {sent_count} notifications for new request in {area}")
    return sent_count


async def send_request_cancelled_notification(
    acceptor_uid: str,
    poster_email: str,
    item: str,
    request_id: str
) -> bool:
    """
    Notify acceptor that request was cancelled
    
    Args:
        acceptor_uid: UID of acceptor
        poster_email: Email of poster who cancelled
        item: Item name
        request_id: Request ID
        
    Returns:
        bool: True if sent successfully
    """
    title = "Request Cancelled ❌"
    body = f"{poster_email} cancelled the request for '{item}'"
    
    data = {
        'type': 'request_cancelled',
        'request_id': request_id,
        'poster_email': poster_email
    }
    
    return await send_notification(acceptor_uid, title, body, data)


async def send_bulk_notification(
    user_uids: List[str],
    title: str,
    body: str,
    data: Optional[Dict] = None
) -> Dict:
    """
    Send notification to multiple users
    
    Args:
        user_uids: List of user UIDs
        title: Notification title
        body: Notification body
        data: Optional data payload
        
    Returns:
        dict: Statistics about sent notifications
    """
    success_count = 0
    failure_count = 0
    
    for uid in user_uids:
        if await send_notification(uid, title, body, data):
            success_count += 1
        else:
            failure_count += 1
    
    return {
        'total': len(user_uids),
        'success': success_count,
        'failed': failure_count
    }


async def remove_fcm_token(user_uid: str) -> Dict:
    """
    Remove FCM token for a user (on logout)
    
    Args:
        user_uid: User UID
        
    Returns:
        dict: Success response
    """
    user_ref = db.collection('users').document(user_uid)
    
    user_ref.update({
        'fcm_token': firestore.DELETE_FIELD,
        'updated_at': datetime.utcnow()
    })
    
    logger.info(f"FCM token removed for user {user_uid}")
    
    return {
        'success': True,
        'message': 'FCM token removed successfully'
    }