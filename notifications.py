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
    
    logger.info(f"✅ FCM token registered for user {user_uid}")

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


async def get_user_info(user_uid: str) -> Optional[Dict]:
    """
    Get user information including name and email

    Args:
        user_uid: User UID

    Returns:
        dict: User info with name, email, etc.
    """
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()

    if not user_doc.exists:
        return None

    return user_doc.to_dict()


async def send_notification(
    user_uid: str,
    title: str,
    body: str,
    data: Optional[Dict] = None,
    channel_id: Optional[str] = None
) -> bool:
    """
    Send premium push notification to a user

    Args:
        user_uid: User UID to send notification to
        title: Notification title
        body: Notification body (uses NAME not email!)
        data: Additional data payload
        priority: Notification priority ("high" or "normal")
        channel_id: Android notification channel ID

    Returns:
        bool: True if sent successfully
    """
    fcm_token = await get_user_fcm_token(user_uid)

    if not fcm_token:
        logger.warning(f"⚠️ No FCM token found for user {user_uid}")
        return False

    try:
        # Build Android-specific config for premium experience
        android_config = messaging.AndroidConfig(
            notification=messaging.AndroidNotification(
                sound='default',
                channel_id=channel_id or 'new_delivery_requests',
                color='#14B8A6',  # Teal color
                default_sound=True,
                default_vibrate_timings=True,
                default_light_settings=True
            )
        )

        # Create notification message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data or {},
            token=fcm_token,
            android=android_config
        )

        # Send message
        response = messaging.send(message)
        logger.info(f"✅ Notification sent to {user_uid}: {response}")

        return True

    except messaging.UnregisteredError:
        logger.warning(f"⚠️ FCM token invalid for user {user_uid}, removing token")
        # Remove invalid token
        user_ref = db.collection('users').document(user_uid)
        user_ref.update({'fcm_token': firestore.DELETE_FIELD})
        return False

    except Exception as e:
        logger.error(f"❌ Error sending notification to {user_uid}: {str(e)}")
        return False


async def send_request_accepted_notification(
    poster_uid: str,
    acceptor_uid: str,
    item: List[str],
    request_id: str
) -> bool:
    """
    Notify poster that their request was accepted
    Uses acceptor's NAME instead of email

    Args:
        poster_uid: UID of request poster
        acceptor_uid: UID of person who accepted
        item: List of items
        request_id: Request ID

    Returns:
        bool: True if sent successfully
    """
    # Get acceptor's NAME (not email!)
    acceptor_info = await get_user_info(acceptor_uid)
    if not acceptor_info:
        logger.error(f"❌ Could not find acceptor info for {acceptor_uid}")
        return False

    acceptor_name = acceptor_info.get('name', acceptor_info.get('email', 'Someone'))

    # Create rich notification
    title = "🎉 Request Accepted!"
    items_text = ", ".join(item[:2])  # Show first 2 items
    if len(item) > 2:
        items_text += f" +{len(item) - 2} more"

    body = f"{acceptor_name} accepted your request for '{items_text}'"

    data = {
        'type': 'request_accepted',
        'title': title,
        'body': body,
        'order_id': request_id,
        'request_id': request_id,
        'acceptor_name': acceptor_name,
        'acceptor_email': acceptor_info.get('email', ''),
        'items': ', '.join(item)
    }

    return await send_notification(
        poster_uid,
        title,
        body,
        data,
        channel_id="order_updates"
    )


async def send_delivery_completed_notification(
    poster_uid: str,
    deliverer_uid: str,
    item: List[str],
    request_id: str
) -> bool:
    """
    Notify poster that delivery is completed
    Uses deliverer's NAME instead of email

    Args:
        poster_uid: UID of request poster
        deliverer_uid: UID of deliverer
        item: List of items
        request_id: Request ID

    Returns:
        bool: True if sent successfully
    """
    # Get deliverer's NAME (not email!)
    deliverer_info = await get_user_info(deliverer_uid)
    if not deliverer_info:
        logger.error(f"❌ Could not find deliverer info for {deliverer_uid}")
        return False

    deliverer_name = deliverer_info.get('name', deliverer_info.get('email', 'Someone'))

    # Create rich notification
    title = "✅ Delivery Completed!"
    items_text = ", ".join(item[:2])
    if len(item) > 2:
        items_text += f" +{len(item) - 2} more"

    body = f"{deliverer_name} completed delivery of '{items_text}'"

    data = {
        'type': 'request_completed',
        'title': title,
        'body': body,
        'order_id': request_id,
        'request_id': request_id,
        'deliverer_name': deliverer_name,
        'deliverer_email': deliverer_info.get('email', ''),
        'items': ', '.join(item)
    }

    return await send_notification(
        poster_uid,
        title,
        body,
        data,
        channel_id="order_updates"
    )


async def send_new_request_in_area_notification(
    area: str,
    item: List[str],
    request_id: str,
    exclude_uid: str,
    poster_uid: Optional[str] = None,
    pickup_area: Optional[str] = None,
    drop_area: Optional[str] = None,
    reward: Optional[int] = None,
    deadline: Optional[str] = None
) -> int:
    """
    PREMIUM: Notify users about new delivery request
    Uses POSTER'S NAME, rich content, smart targeting

    Args:
        area: Area where request is posted (for backward compatibility)
        item: List of items to deliver
        request_id: Request ID
        exclude_uid: UID to exclude (poster)
        poster_uid: UID of request poster (optional, for getting name)
        pickup_area: Pickup location area (optional)
        drop_area: Drop location area (optional)
        reward: Reward amount (optional)
        deadline: Optional deadline

    Returns:
        int: Number of notifications sent
    """
    # Get poster's NAME (not email!)
    poster_name = 'Someone'
    if poster_uid:
        poster_info = await get_user_info(poster_uid)
        if poster_info:
            poster_name = poster_info.get('name', 'Someone')

    # Use provided areas or fallback to area parameter
    target_pickup = pickup_area or area
    target_drop = drop_area or area

    # Get all reachable users
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_reachable', '==', True))

    # Create premium notification content
    title = "🛒 New Delivery Request"
    items_text = ", ".join(item[:2])
    if len(item) > 2:
        items_text += f" +{len(item) - 2} more"

    # Use NAME not email!
    body = f"{poster_name} needs delivery from {target_pickup}"

    # Rich data payload for Android app
    data = {
        'type': 'new_request',
        'title': title,
        'body': body,
        'order_id': request_id,
        'request_id': request_id,
        'poster_name': poster_name,
        'pickup_area': target_pickup,
        'drop_area': target_drop,
        'items': ', '.join(item),
        'reward': str(reward) if reward else '',
        'deadline': deadline or ''
    }

    sent_count = 0

    # Target users in BOTH pickup and drop areas
    target_areas = [target_pickup]
    if target_drop and target_drop != target_pickup:
        target_areas.append(target_drop)

    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        user_uid = user_data.get('uid')

        # Skip poster themselves
        if user_uid == exclude_uid:
            continue

        # Check if user has either area in preferences
        preferred_areas = user_data.get('preferred_areas', [])
        has_matching_area = any(target_area in preferred_areas for target_area in target_areas)

        if not has_matching_area:
            continue

        # Send HIGH PRIORITY notification
        if await send_notification(
            user_uid,
            title,
            body,
            data,
            channel_id="new_delivery_requests"
        ):
            sent_count += 1

    logger.info(f"✅ Sent {sent_count} premium notifications for new request in {target_pickup} → {target_drop}")
    logger.info(f"📦 Items: {items_text} | 💰 Reward: ₹{reward if reward else 'N/A'}")

    return sent_count


async def send_request_cancelled_notification(
    acceptor_uid: str,
    poster_uid: str,
    item: List[str],
    request_id: str
) -> bool:
    """
    Notify acceptor that request was cancelled
    Uses poster's NAME instead of email

    Args:
        acceptor_uid: UID of acceptor
        poster_uid: UID of poster who cancelled
        item: List of items
        request_id: Request ID

    Returns:
        bool: True if sent successfully
    """
    # Get poster's NAME (not email!)
    poster_info = await get_user_info(poster_uid)
    if not poster_info:
        logger.error(f"❌ Could not find poster info for {poster_uid}")
        return False

    poster_name = poster_info.get('name', poster_info.get('email', 'Someone'))

    # Create notification
    title = "❌ Request Cancelled"
    items_text = ", ".join(item[:2])
    if len(item) > 2:
        items_text += f" +{len(item) - 2} more"

    body = f"{poster_name} cancelled the request for '{items_text}'"

    data = {
        'type': 'request_cancelled',
        'title': title,
        'body': body,
        'order_id': request_id,
        'request_id': request_id,
        'poster_name': poster_name,
        'poster_email': poster_info.get('email', ''),
        'items': ', '.join(item)
    }

    return await send_notification(
        acceptor_uid,
        title,
        body,
        data,
        channel_id="order_updates"
    )


async def send_bulk_notification(
    user_uids: List[str],
    title: str,
    body: str,
    data: Optional[Dict] = None,
) -> Dict:
    """
    Send premium notification to multiple users

    Args:
        user_uids: List of user UIDs
        title: Notification title
        body: Notification body
        data: Optional data payload
        priority: Notification priority

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

    logger.info(f"📊 Bulk notification: {success_count} sent, {failure_count} failed")

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

    logger.info(f"✅ FCM token removed for user {user_uid}")
    
    return {
        'success': True,
        'message': 'FCM token removed successfully'
    }