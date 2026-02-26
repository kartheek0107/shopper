"""
Push Notifications System using Firebase Cloud Messaging (FCM)
Handles notification sending for request events
"""

from typing import Optional, Dict, List
from firebase_admin import messaging, firestore
from datetime import datetime
from fastapi import HTTPException
import asyncio
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Firestore client
db = firestore.client()

VISIBILITY_PRIVATE = "private"
VISIBILITY_PUBLIC = "public"
VISIBILITY_SECRET = "secret"

# ─────────────────────────────────────────────────────────────────────────────
# FIX: Channel IDs must match the _v2 constants in FCMService.kt / NotificationManager.kt.
#
# Android channel importance is WRITE-ONCE per device. The original IDs were
# registered on test devices with IMPORTANCE_DEFAULT, which permanently blocks
# heads-up banners on those devices. Bumping to _v2 forces Android to treat them
# as brand-new channels and respect IMPORTANCE_HIGH from the first registration.
# ─────────────────────────────────────────────────────────────────────────────
CHANNEL_NEW_REQUESTS = "new_delivery_requests_v2"
CHANNEL_ORDER_UPDATES = "order_updates_v2"
CHANNEL_GENERAL = "general_notifications_v2"


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
    Send push notification to a user.

    Args:
        user_uid: User UID to send notification to
        title: Notification title
        body: Notification body (uses NAME not email!)
        data: Additional data payload
        channel_id: Android notification channel ID

    Returns:
        bool: True if sent successfully
    """
    fcm_token = await get_user_fcm_token(user_uid)

    if not fcm_token:
        logger.warning(f"⚠️ No FCM token found for user {user_uid}")
        return False

    try:
        # ─────────────────────────────────────────────────────────────────
        # FIX: DATA-ONLY PAYLOAD — no notification block anywhere.
        #
        # The original code had TWO notification blocks:
        #   1. messaging.Notification(title=..., body=...) at the top level
        #   2. messaging.AndroidNotification(...) inside AndroidConfig
        #
        # When FCM receives a message with ANY notification block and the app
        # is in the background, Google's Firebase SDK intercepts it and
        # displays it directly using whatever the system default channel is —
        # completely bypassing onMessageReceived() and all our custom
        # IMPORTANCE_HIGH channel logic. The result: silent, uncategorised
        # notifications that never show as heads-up banners.
        #
        # Fix: remove BOTH notification blocks entirely. Put title + body
        # inside the `data` dict instead. The Android app's FCMService reads
        # them from data["title"] and data["body"] in onMessageReceived().
        # priority='high' in AndroidConfig is the FCM transport priority —
        # it wakes the device up to deliver the message immediately.
        # ─────────────────────────────────────────────────────────────────

        # Merge title + body into the data payload so onMessageReceived gets them
        full_data = {
            'title': title,
            'body': body,
            **(data or {})
        }

        # Ensure all values are strings — FCM data payload only accepts str
        full_data = {k: str(v) for k, v in full_data.items() if v is not None}

        android_config = messaging.AndroidConfig(
            priority='high',          # FCM transport priority: wakes device immediately
            # NO notification= block here — that was the bug
        )

        message = messaging.Message(
            # NO notification= block here — that was the bug
            data=full_data,
            token=fcm_token,
            android=android_config
        )

        # Run in executor to avoid blocking the async event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, messaging.send, message)
        logger.info(f"✅ Notification sent to {user_uid}: {response}")

        return True

    except messaging.UnregisteredError:
        logger.warning(f"⚠️ FCM token invalid for user {user_uid}, removing token")
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
    Notify poster that their request was accepted.
    Uses acceptor's NAME instead of email.

    Args:
        poster_uid: UID of request poster
        acceptor_uid: UID of person who accepted
        item: List of items
        request_id: Request ID

    Returns:
        bool: True if sent successfully
    """
    acceptor_info = await get_user_info(acceptor_uid)
    if not acceptor_info:
        logger.error(f"❌ Could not find acceptor info for {acceptor_uid}")
        return False

    acceptor_name = acceptor_info.get('name', acceptor_info.get('email', 'Someone'))

    title = "🎉 Request Accepted!"
    items_text = ", ".join(item[:2])
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
        channel_id=CHANNEL_ORDER_UPDATES
    )


async def send_delivery_completed_notification(
    poster_uid: str,
    deliverer_uid: str,
    item: List[str],
    request_id: str
) -> bool:
    """
    Notify poster that delivery is completed.
    Uses deliverer's NAME instead of email.

    Args:
        poster_uid: UID of request poster
        deliverer_uid: UID of deliverer
        item: List of items
        request_id: Request ID

    Returns:
        bool: True if sent successfully
    """
    deliverer_info = await get_user_info(deliverer_uid)
    if not deliverer_info:
        logger.error(f"❌ Could not find deliverer info for {deliverer_uid}")
        return False

    deliverer_name = deliverer_info.get('name', deliverer_info.get('email', 'Someone'))

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
        channel_id=CHANNEL_ORDER_UPDATES
    )


async def send_request_cancelled_notification(
    acceptor_uid: str,
    poster_uid: str,
    item: List[str],
    request_id: str
) -> bool:
    """
    Notify acceptor that request was cancelled.
    Uses poster's NAME instead of email.

    Args:
        acceptor_uid: UID of acceptor
        poster_uid: UID of poster who cancelled
        item: List of items
        request_id: Request ID

    Returns:
        bool: True if sent successfully
    """
    poster_info = await get_user_info(poster_uid)
    if not poster_info:
        logger.error(f"❌ Could not find poster info for {poster_uid}")
        return False

    poster_name = poster_info.get('name', poster_info.get('email', 'Someone'))

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
        channel_id=CHANNEL_ORDER_UPDATES
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
    Notify ALL REACHABLE users about a new delivery request.
    Uses poster's NAME, rich content.

    Args:
        area: Area where request is posted (backward compatibility)
        item: List of items to deliver
        request_id: Request ID
        exclude_uid: UID to exclude (the poster themselves)
        poster_uid: UID of request poster (for getting name)
        pickup_area: Pickup location area
        drop_area: Drop location area
        reward: Reward amount
        deadline: Optional deadline string

    Returns:
        int: Number of notifications sent
    """
    poster_name = 'Someone'
    if poster_uid:
        poster_info = await get_user_info(poster_uid)
        if poster_info:
            poster_name = poster_info.get('name', 'Someone')

    target_pickup = pickup_area or area
    target_drop = drop_area or area

    # Query all reachable users — no area filtering
    users_ref = db.collection('users')
    query = users_ref.where(filter=firestore.FieldFilter('is_reachable', '==', True))

    title = "🛒 New Delivery Request"
    items_text = ", ".join(item[:2])
    if len(item) > 2:
        items_text += f" +{len(item) - 2} more"

    body = f"{poster_name} needs delivery from {target_pickup}"

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

    for user_doc in query.stream():
        user_data = user_doc.to_dict()
        user_uid = user_data.get('uid')

        # Skip the poster themselves
        if user_uid == exclude_uid:
            continue

        if await send_notification(
            user_uid,
            title,
            body,
            data,
            channel_id=CHANNEL_NEW_REQUESTS
        ):
            sent_count += 1

    logger.info(f"✅ Sent {sent_count} notifications to ALL reachable users")
    logger.info(f"📦 Request: {target_pickup} → {target_drop} | Items: {items_text} | 💰 Reward: ₹{reward if reward else 'N/A'}")

    return sent_count


async def send_bulk_notification(
    user_uids: List[str],
    title: str,
    body: str,
    data: Optional[Dict] = None,
) -> Dict:
    """
    Send notification to multiple users.

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

    logger.info(f"📊 Bulk notification: {success_count} sent, {failure_count} failed")

    return {
        'total': len(user_uids),
        'success': success_count,
        'failed': failure_count
    }


async def remove_fcm_token(user_uid: str) -> Dict:
    """
    Remove FCM token for a user (on logout).

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