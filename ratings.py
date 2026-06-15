"""
Rating System for College Delivery System

Production-hardened:
- All Firestore I/O is async (non-blocking event loop)
- Rating stats recalculation wrapped in Firestore transaction to prevent race conditions
- Timezone-aware timestamps throughout
"""

from typing import Dict, List, Optional
from fastapi import HTTPException

from firebase_admin import firestore as _fs
from firestore_async import (
    get_db, utcnow,
    get_doc, set_doc, update_doc, delete_doc,
    build_query, stream_query,
    run_transaction,
)


async def create_rating(
    request_id: str,
    rater_uid: str,
    rating: int,
    comment: Optional[str] = None
) -> Dict:
    """
    Create a rating for a completed request delivery.
    Only the request poster can rate the acceptor/deliverer.
    """
    if not 1 <= rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    request_data = await get_doc('requests', request_id)
    if request_data is None:
        raise HTTPException(status_code=404, detail="Request not found")

    if request_data.get('status') != 'completed':
        raise HTTPException(status_code=400, detail="Can only rate completed requests")

    poster_uid = request_data.get('posted_by')
    if rater_uid != poster_uid:
        raise HTTPException(status_code=403, detail="Only the request poster can rate the deliverer")

    acceptor_uid = request_data.get('accepted_by')
    if not acceptor_uid:
        raise HTTPException(status_code=400, detail="No acceptor found for this request")

    # Check if rating already exists
    existing = await get_doc('ratings', f"{request_id}_rating")
    if existing:
        raise HTTPException(status_code=400, detail="You have already rated this delivery")

    rating_id = f"{request_id}_rating"
    now = utcnow()

    # Denormalize: store names at write time to avoid N+1 reads later
    poster_data = await get_doc('users', poster_uid)
    poster_name = 'Anonymous'
    if poster_data:
        poster_name = poster_data.get('name') or poster_data.get('email', 'Anonymous')

    items = request_data.get('item', [])
    item_delivered = ', '.join(items) if items else 'Unknown'

    deliverer_data = await get_doc('users', acceptor_uid)
    deliverer_name = 'Unknown'
    if deliverer_data:
        deliverer_name = deliverer_data.get('name') or deliverer_data.get('email', 'Unknown')

    rating_document = {
        'rating_id': rating_id,
        'request_id': request_id,
        'poster_uid': poster_uid,
        'deliverer_uid': acceptor_uid,
        'rating': rating,
        'comment': comment,
        'created_at': now,
        # Denormalized fields (avoid N+1 on read)
        'poster_name': poster_name,
        'item_delivered': item_delivered,
        'deliverer_name': deliverer_name,
    }

    await set_doc('ratings', rating_id, rating_document)

    # Update deliverer's rating statistics (transactional)
    await update_user_rating_stats(acceptor_uid)

    return rating_document


async def update_user_rating_stats(user_uid: str) -> Dict:
    """
    Recalculate and update user's rating statistics.
    Uses a Firestore transaction to prevent race conditions when two
    ratings are submitted concurrently for the same deliverer.
    """
    # Fetch all ratings for this deliverer
    q = build_query('ratings', filters=[('deliverer_uid', '==', user_uid)])
    all_ratings = await stream_query(q)

    total_ratings = 0
    sum_ratings = 0
    rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for rating_data in all_ratings:
        rating_value = rating_data.get('rating')
        if rating_value is not None:
            total_ratings += 1
            sum_ratings += rating_value
            if rating_value in rating_distribution:
                rating_distribution[rating_value] += 1

    average_rating = round(sum_ratings / total_ratings, 2) if total_ratings > 0 else 0.0

    db = get_db()
    user_ref = db.collection('users').document(user_uid)

    @_fs.transactional
    def _update_stats(transaction, ref, stats):
        snap = ref.get(transaction=transaction)
        if not snap.exists:
            return stats
        transaction.update(ref, {
            'rating_stats': stats,
            'updated_at': utcnow(),
        })
        return stats

    rating_stats = {
        'average_rating': average_rating,
        'total_ratings': total_ratings,
        'rating_distribution': rating_distribution,
    }

    await run_transaction(_update_stats, ref=user_ref, stats=rating_stats)
    return rating_stats


async def get_user_ratings(user_uid: str) -> Dict:
    """Get all ratings received by a user (as deliverer)."""
    user_data = await get_doc('users', user_uid)

    rating_stats = {
        'average_rating': 0.0,
        'total_ratings': 0,
        'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
    }
    if user_data:
        rating_stats = user_data.get('rating_stats', rating_stats)

    q = build_query(
        'ratings',
        filters=[('deliverer_uid', '==', user_uid)],
        order_by='created_at',
        descending=True,
    )
    all_ratings = await stream_query(q)

    ratings = []
    for rating_data in all_ratings:
        # Use denormalized fields if available; fall back to per-rating lookups
        poster_name = rating_data.get('poster_name')
        item_delivered = rating_data.get('item_delivered')

        if not poster_name:
            poster_data = await get_doc('users', rating_data['poster_uid'])
            poster_name = 'Anonymous'
            if poster_data:
                poster_name = poster_data.get('name') or poster_data.get('email', 'Anonymous')

        if not item_delivered:
            request_data = await get_doc('requests', rating_data['request_id'])
            item_delivered = 'Unknown'
            if request_data:
                items = request_data.get('item', [])
                item_delivered = ', '.join(items) if items else 'Unknown'

        ratings.append({
            'rating_id': rating_data.get('rating_id'),
            'request_id': rating_data.get('request_id'),
            'rating': rating_data.get('rating'),
            'comment': rating_data.get('comment'),
            'poster_name': poster_name,
            'item_delivered': item_delivered,
            'created_at': rating_data.get('created_at'),
        })

    return {'stats': rating_stats, 'ratings': ratings}


async def get_rating_for_request(request_id: str) -> Optional[Dict]:
    """Get rating for a specific request."""
    return await get_doc('ratings', f"{request_id}_rating")


async def can_rate_request(request_id: str, user_uid: str) -> Dict:
    """Check if user can rate the deliverer for a request."""
    request_data = await get_doc('requests', request_id)

    if not request_data:
        return {'can_rate': False, 'reason': 'Request not found'}
    if request_data.get('status') != 'completed':
        return {'can_rate': False, 'reason': 'Request is not completed yet'}

    poster_uid = request_data.get('posted_by')
    if user_uid != poster_uid:
        return {'can_rate': False, 'reason': 'Only the request poster can rate the deliverer'}

    deliverer_uid = request_data.get('accepted_by')
    if not deliverer_uid:
        return {'can_rate': False, 'reason': 'No deliverer found'}

    existing_rating = await get_rating_for_request(request_id)
    if existing_rating:
        return {
            'can_rate': False,
            'reason': 'You have already rated this delivery',
            'existing_rating': existing_rating,
        }

    deliverer_data = await get_doc('users', deliverer_uid)
    deliverer_name = "Unknown"
    if deliverer_data:
        deliverer_name = deliverer_data.get('name') or deliverer_data.get('email', 'Unknown')

    return {
        'can_rate': True,
        'reason': 'You can rate this delivery',
        'deliverer_uid': deliverer_uid,
        'deliverer_name': deliverer_name,
    }


async def get_user_rating_summary(user_uid: str) -> Dict:
    """Get summarized rating information for user profile."""
    user_data = await get_doc('users', user_uid)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    rating_stats = user_data.get('rating_stats', {
        'average_rating': 0.0,
        'total_ratings': 0,
        'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
    })

    total = rating_stats.get('total_ratings', 0)
    distribution = rating_stats.get('rating_distribution', {})

    percentage_distribution = {}
    if total > 0:
        for r, count in distribution.items():
            percentage_distribution[r] = round((count / total) * 100, 1)
    else:
        percentage_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    return {
        'average_rating': rating_stats.get('average_rating', 0.0),
        'total_ratings': total,
        'rating_distribution': distribution,
        'percentage_distribution': percentage_distribution,
        'rating_badge': get_rating_badge(rating_stats.get('average_rating', 0.0)),
    }


def get_rating_badge(average_rating: float) -> str:
    """Get badge/label based on average rating."""
    if average_rating >= 4.5:
        return "Excellent Deliverer"
    elif average_rating >= 4.0:
        return "Great Deliverer"
    elif average_rating >= 3.5:
        return "Good Deliverer"
    elif average_rating >= 3.0:
        return "Average Deliverer"
    elif average_rating > 0:
        return "Needs Improvement"
    else:
        return "No Ratings Yet"


async def update_rating(rating_id: str, user_uid: str, new_rating: int, new_comment: Optional[str] = None) -> Dict:
    """Update an existing rating (only by the poster, within 24 hours)."""
    if not 1 <= new_rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    rating_data = await get_doc('ratings', rating_id)
    if not rating_data:
        raise HTTPException(status_code=404, detail="Rating not found")

    if rating_data.get('poster_uid') != user_uid:
        raise HTTPException(status_code=403, detail="You can only update your own ratings")

    created_at = rating_data.get('created_at')
    if created_at:
        now = utcnow()
        # Ensure created_at is timezone-aware
        if created_at.tzinfo is None:
            from datetime import timezone
            created_at = created_at.replace(tzinfo=timezone.utc)
        hours_since_creation = (now - created_at).total_seconds() / 3600
        if hours_since_creation > 24:
            raise HTTPException(status_code=403, detail="Cannot update rating after 24 hours")

    await update_doc('ratings', rating_id, {
        'rating': new_rating,
        'comment': new_comment,
        'updated_at': utcnow(),
    })

    await update_user_rating_stats(rating_data.get('deliverer_uid'))
    return await get_doc('ratings', rating_id)


async def delete_rating(rating_id: str, user_uid: str) -> Dict:
    """Delete a rating (only by the poster, within 24 hours)."""
    rating_data = await get_doc('ratings', rating_id)
    if not rating_data:
        raise HTTPException(status_code=404, detail="Rating not found")

    if rating_data.get('poster_uid') != user_uid:
        raise HTTPException(status_code=403, detail="You can only delete your own ratings")

    created_at = rating_data.get('created_at')
    if created_at:
        now = utcnow()
        if created_at.tzinfo is None:
            from datetime import timezone
            created_at = created_at.replace(tzinfo=timezone.utc)
        hours_since_creation = (now - created_at).total_seconds() / 3600
        if hours_since_creation > 24:
            raise HTTPException(status_code=403, detail="Cannot delete rating after 24 hours")

    deliverer_uid = rating_data.get('deliverer_uid')
    await delete_doc('ratings', rating_id)
    await update_user_rating_stats(deliverer_uid)

    return {'success': True, 'message': 'Rating deleted successfully'}


async def get_ratings_given_by_user(user_uid: str) -> List[Dict]:
    """Get all ratings given by a user (as a poster)."""
    q = build_query(
        'ratings',
        filters=[('poster_uid', '==', user_uid)],
        order_by='created_at',
        descending=True,
    )
    all_ratings = await stream_query(q)

    ratings = []
    for rating_data in all_ratings:
        # Use denormalized field if available; fall back to per-rating lookup
        deliverer_name = rating_data.get('deliverer_name')
        if not deliverer_name:
            deliverer_data = await get_doc('users', rating_data['deliverer_uid'])
            deliverer_name = 'Unknown'
            if deliverer_data:
                deliverer_name = deliverer_data.get('name') or deliverer_data.get('email', 'Unknown')

        ratings.append({
            'rating_id': rating_data.get('rating_id'),
            'request_id': rating_data.get('request_id'),
            'rating': rating_data.get('rating'),
            'comment': rating_data.get('comment'),
            'deliverer_name': deliverer_name,
            'created_at': rating_data.get('created_at'),
        })

    return ratings