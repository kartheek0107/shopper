"""
Push Notifications System using Firebase Cloud Messaging (FCM)

Production-hardened:
- Concurrent FCM dispatch via asyncio.gather with semaphore
- All Firestore I/O is async (non-blocking event loop)
- Timezone-aware timestamps throughout
"""

from typing import Optional, Dict, List
from firebase_admin import messaging, firestore
import asyncio
import logging

from firestore_async import (
    get_db, utcnow,
    get_doc, update_doc,
    build_query, stream_query,
)
from config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VISIBILITY_PRIVATE = "private"
VISIBILITY_PUBLIC = "public"
VISIBILITY_SECRET = "secret"

# Channel IDs must match the _v2 constants in FCMService.kt / NotificationManager.kt.
CHANNEL_NEW_REQUESTS = "new_delivery_requests_v2"
CHANNEL_ORDER_UPDATES = "order_updates_v2"
CHANNEL_GENERAL = "general_notifications_v2"

# Semaphore to limit concurrent FCM API calls
_fcm_semaphore = asyncio.Semaphore(settings.FCM_SEND_CONCURRENCY)


async def register_fcm_token(user_uid: str, fcm_token: str) -> Dict:
    """Register or update FCM token for a user."""
    now = utcnow()
    await update_doc('users', user_uid, {
        'fcm_token': fcm_token,
        'fcm_token_updated_at': now,
        'updated_at': now,
    })
    logger.info(f"✅ FCM token registered for user {user_uid}")
    return {'success': True, 'message': 'FCM token registered successfully'}


async def get_user_fcm_token(user_uid: str) -> Optional[str]:
    """Get FCM token for a user."""
    user_data = await get_doc('users', user_uid)
    if not user_data:
        return None
    return user_data.get('fcm_token')


async def get_user_info(user_uid: str) -> Optional[Dict]:
    """Get user information including name and email."""
    return await get_doc('users', user_uid)


async def send_notification(
    user_uid: str,
    title: str,
    body: str,
    data: Optional[Dict] = None,
    channel_id: Optional[str] = None
) -> bool:
    """
    Send push notification to a user (data-only payload).
    Uses a semaphore to limit concurrent FCM calls.
    """
    fcm_token = await get_user_fcm_token(user_uid)
    if not fcm_token:
        logger.warning(f"⚠️ No FCM token found for user {user_uid}")
        return False

    try:
        full_data = {'title': title, 'body': body, **(data or {})}
        full_data = {k: str(v) for k, v in full_data.items() if v is not None}

        android_config = messaging.AndroidConfig(priority='high')
        message = messaging.Message(
            data=full_data,
            token=fcm_token,
            android=android_config,
        )

        async with _fcm_semaphore:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, messaging.send, message)

        logger.info(f"✅ Notification sent to {user_uid}: {response}")
        return True

    except messaging.UnregisteredError:
        logger.warning(f"⚠️ FCM token invalid for user {user_uid}, removing token")
        try:
            await update_doc('users', user_uid, {'fcm_token': firestore.DELETE_FIELD})
        except Exception:
            pass
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
    """Notify poster that their request was accepted (uses acceptor's NAME)."""
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
        'title': title, 'body': body,
        'order_id': request_id, 'request_id': request_id,
        'acceptor_name': acceptor_name,
        'acceptor_email': acceptor_info.get('email', ''),
        'items': ', '.join(item),
    }

    return await send_notification(poster_uid, title, body, data, channel_id=CHANNEL_ORDER_UPDATES)


async def send_delivery_completed_notification(
    poster_uid: str,
    deliverer_uid: str,
    item: List[str],
    request_id: str
) -> bool:
    """Notify poster that delivery is completed (uses deliverer's NAME)."""
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
        'title': title, 'body': body,
        'order_id': request_id, 'request_id': request_id,
        'deliverer_name': deliverer_name,
        'deliverer_email': deliverer_info.get('email', ''),
        'items': ', '.join(item),
    }

    return await send_notification(poster_uid, title, body, data, channel_id=CHANNEL_ORDER_UPDATES)


async def send_request_cancelled_notification(
    acceptor_uid: str,
    poster_uid: str,
    item: List[str],
    request_id: str
) -> bool:
    """Notify acceptor that request was cancelled (uses poster's NAME)."""
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
        'title': title, 'body': body,
        'order_id': request_id, 'request_id': request_id,
        'poster_name': poster_name,
        'poster_email': poster_info.get('email', ''),
        'items': ', '.join(item),
    }

    return await send_notification(acceptor_uid, title, body, data, channel_id=CHANNEL_ORDER_UPDATES)


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
    Uses asyncio.gather for concurrent dispatch.
    """
    poster_name = 'Someone'
    if poster_uid:
        poster_info = await get_user_info(poster_uid)
        if poster_info:
            poster_name = poster_info.get('name', 'Someone')

    target_pickup = pickup_area or area
    target_drop = drop_area or area

    # Optimized: query only users in relevant areas instead of ALL reachable users.
    # If specific areas are known, fetch only those users (typically 10-50 vs 600+).
    target_areas = set()
    if target_pickup:
        target_areas.add(target_pickup)
    if target_drop:
        target_areas.add(target_drop)

    if target_areas:
        # Fetch users per area and merge (avoids full-collection scan)
        import asyncio as _aio
        area_queries = []
        for ta in target_areas:
            area_queries.append(
                stream_query(build_query('users', filters=[
                    ('is_reachable', '==', True),
                    ('current_area', '==', ta),
                ]))
            )
        area_results = await _aio.gather(*area_queries)

        # Deduplicate by uid
        seen_uids = set()
        reachable_users = []
        for users in area_results:
            for u in users:
                uid = u.get('uid')
                if uid and uid not in seen_uids:
                    seen_uids.add(uid)
                    reachable_users.append(u)
    else:
        # Fallback: no area info — query all reachable users
        q = build_query('users', filters=[('is_reachable', '==', True)])
        reachable_users = await stream_query(q)

    title = "🛒 New Delivery Request"
    items_text = ", ".join(item[:2])
    if len(item) > 2:
        items_text += f" +{len(item) - 2} more"
    body = f"{poster_name} needs delivery from {target_pickup}"

    data = {
        'type': 'new_request',
        'title': title, 'body': body,
        'order_id': request_id, 'request_id': request_id,
        'poster_name': poster_name,
        'pickup_area': target_pickup, 'drop_area': target_drop,
        'items': ', '.join(item),
        'reward': str(reward) if reward else '',
        'deadline': deadline or '',
    }

    # Build list of notification coroutines (skip the poster)
    tasks = []
    for user_data in reachable_users:
        user_uid = user_data.get('uid')
        if user_uid == exclude_uid:
            continue
        tasks.append(send_notification(user_uid, title, body, data, channel_id=CHANNEL_NEW_REQUESTS))

    if not tasks:
        return 0

    # Fire all notifications concurrently (semaphore inside send_notification limits parallelism)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    sent_count = sum(1 for r in results if r is True)

    logger.info(f"✅ Sent {sent_count}/{len(tasks)} notifications concurrently")
    logger.info(
        f"📦 Request: {target_pickup} → {target_drop} | Items: {items_text} "
        f"| 💰 Reward: ₹{reward if reward else 'N/A'}"
    )

    return sent_count


async def send_bulk_notification(
    user_uids: List[str],
    title: str,
    body: str,
    data: Optional[Dict] = None,
) -> Dict:
    """Send notification to multiple users concurrently."""
    tasks = [send_notification(uid, title, body, data) for uid in user_uids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = sum(1 for r in results if r is True)
    failure_count = len(results) - success_count

    logger.info(f"📊 Bulk notification: {success_count} sent, {failure_count} failed")
    return {'total': len(user_uids), 'success': success_count, 'failed': failure_count}


async def remove_fcm_token(user_uid: str) -> Dict:
    """Remove FCM token for a user (on logout)."""
    await update_doc('users', user_uid, {
        'fcm_token': firestore.DELETE_FIELD,
        'updated_at': utcnow(),
    })
    logger.info(f"✅ FCM token removed for user {user_uid}")
    return {'success': True, 'message': 'FCM token removed successfully'}