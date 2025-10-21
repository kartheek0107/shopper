"""
Rating System for College Delivery System
Allows request posters to rate delivery acceptors after completion
"""

from typing import Dict, List, Optional
from firebase_admin import firestore
from datetime import datetime
from fastapi import HTTPException

# Get Firestore client
db = firestore.client()


async def create_rating(
    request_id: str,
    rater_uid: str,
    rating: int,
    comment: Optional[str] = None
) -> Dict:
    """
    Create a rating for a completed request delivery
    Only the request poster can rate the acceptor/deliverer
    
    Args:
        request_id: ID of the completed request
        rater_uid: UID of user giving the rating (must be poster)
        rating: Rating value (1-5)
        comment: Optional comment/feedback
        
    Returns:
        dict: Created rating data
        
    Raises:
        HTTPException: If validation fails
    """
    # Validate rating value
    if not 1 <= rating <= 5:
        raise HTTPException(
            status_code=400,
            detail="Rating must be between 1 and 5"
        )
    
    # Get the request
    request_ref = db.collection('requests').document(request_id)
    request_doc = request_ref.get()
    
    if not request_doc.exists:
        raise HTTPException(status_code=404, detail="Request not found")
    
    request_data = request_doc.to_dict()
    
    # Verify request is completed
    if request_data.get('status') != 'completed':
        raise HTTPException(
            status_code=400,
            detail="Can only rate completed requests"
        )
    
    # Verify the rater is the poster
    poster_uid = request_data.get('posted_by')
    if rater_uid != poster_uid:
        raise HTTPException(
            status_code=403,
            detail="Only the request poster can rate the deliverer"
        )
    
    # Get the acceptor (person who delivered)
    acceptor_uid = request_data.get('accepted_by')
    if not acceptor_uid:
        raise HTTPException(
            status_code=400,
            detail="No acceptor found for this request"
        )
    
    # Check if rating already exists
    ratings_ref = db.collection('ratings')
    existing_query = ratings_ref.where(
        filter=firestore.FieldFilter('request_id', '==', request_id)
    )
    
    existing_ratings = list(existing_query.stream())
    if existing_ratings:
        raise HTTPException(
            status_code=400,
            detail="You have already rated this delivery"
        )
    
    # Create rating document
    rating_id = f"{request_id}_rating"
    rating_document = {
        'rating_id': rating_id,
        'request_id': request_id,
        'poster_uid': poster_uid,
        'deliverer_uid': acceptor_uid,
        'rating': rating,
        'comment': comment,
        'created_at': datetime.utcnow()
    }
    
    # Store rating
    ratings_ref.document(rating_id).set(rating_document)
    
    # Update deliverer's rating statistics
    await update_user_rating_stats(acceptor_uid)
    
    return rating_document


async def update_user_rating_stats(user_uid: str) -> Dict:
    """
    Recalculate and update user's rating statistics
    These are ratings received as a deliverer
    
    Args:
        user_uid: UID of deliverer to update
        
    Returns:
        dict: Updated rating stats
    """
    ratings_ref = db.collection('ratings')
    query = ratings_ref.where(filter=firestore.FieldFilter('deliverer_uid', '==', user_uid))
    
    total_ratings = 0
    sum_ratings = 0
    rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    
    for doc in query.stream():
        rating_data = doc.to_dict()
        rating_value = rating_data.get('rating')
        
        total_ratings += 1
        sum_ratings += rating_value
        rating_distribution[rating_value] += 1
    
    # Calculate average
    average_rating = round(sum_ratings / total_ratings, 2) if total_ratings > 0 else 0.0
    
    # Update user document
    user_ref = db.collection('users').document(user_uid)
    rating_stats = {
        'rating_stats': {
            'average_rating': average_rating,
            'total_ratings': total_ratings,
            'rating_distribution': rating_distribution
        },
        'updated_at': datetime.utcnow()
    }
    
    user_ref.update(rating_stats)
    
    return rating_stats['rating_stats']


async def get_user_ratings(user_uid: str) -> Dict:
    """
    Get all ratings received by a user (as deliverer)
    
    Args:
        user_uid: UID of deliverer
        
    Returns:
        dict: User's rating statistics and individual ratings
    """
    # Get rating stats from user document
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()
    
    rating_stats = {
        'average_rating': 0.0,
        'total_ratings': 0,
        'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    }
    
    if user_doc.exists:
        user_data = user_doc.to_dict()
        rating_stats = user_data.get('rating_stats', rating_stats)
    
    # Get individual ratings
    ratings_ref = db.collection('ratings')
    query = ratings_ref.where(
        filter=firestore.FieldFilter('deliverer_uid', '==', user_uid)
    ).order_by('created_at', direction=firestore.Query.DESCENDING)
    
    ratings = []
    for doc in query.stream():
        rating_data = doc.to_dict()
        
        # Get poster's name
        poster_ref = db.collection('users').document(rating_data['poster_uid'])
        poster_doc = poster_ref.get()
        poster_name = "Anonymous"
        if poster_doc.exists:
            poster_data = poster_doc.to_dict()
            poster_name = poster_data.get('name') or poster_data.get('email', 'Anonymous')
        
        # Get request details
        request_ref = db.collection('requests').document(rating_data['request_id'])
        request_doc = request_ref.get()
        item_delivered = "Unknown"
        if request_doc.exists:
            request_data = request_doc.to_dict()
            items = request_data.get('item', [])
            item_delivered = ", ".join(items) if items else "Unknown"
        
        ratings.append({
            'rating_id': rating_data.get('rating_id'),
            'request_id': rating_data.get('request_id'),
            'rating': rating_data.get('rating'),
            'comment': rating_data.get('comment'),
            'poster_name': poster_name,
            'item_delivered': item_delivered,
            'created_at': rating_data.get('created_at')
        })
    
    return {
        'stats': rating_stats,
        'ratings': ratings
    }


async def get_rating_for_request(request_id: str) -> Optional[Dict]:
    """
    Get rating for a specific request
    
    Args:
        request_id: Request ID
        
    Returns:
        dict: Rating if exists, None otherwise
    """
    rating_ref = db.collection('ratings').document(f"{request_id}_rating")
    rating_doc = rating_ref.get()
    
    if rating_doc.exists:
        return rating_doc.to_dict()
    return None


async def can_rate_request(request_id: str, user_uid: str) -> Dict:
    """
    Check if user can rate the deliverer for a request
    
    Args:
        request_id: Request ID
        user_uid: User UID (must be poster)
        
    Returns:
        dict: Whether user can rate and reason
    """
    # Get request
    request_ref = db.collection('requests').document(request_id)
    request_doc = request_ref.get()
    
    if not request_doc.exists:
        return {
            'can_rate': False,
            'reason': 'Request not found'
        }
    
    request_data = request_doc.to_dict()
    
    # Check if completed
    if request_data.get('status') != 'completed':
        return {
            'can_rate': False,
            'reason': 'Request is not completed yet'
        }
    
    # Check if user is the poster
    poster_uid = request_data.get('posted_by')
    if user_uid != poster_uid:
        return {
            'can_rate': False,
            'reason': 'Only the request poster can rate the deliverer'
        }
    
    # Check if deliverer exists
    deliverer_uid = request_data.get('accepted_by')
    if not deliverer_uid:
        return {
            'can_rate': False,
            'reason': 'No deliverer found'
        }
    
    # Check if already rated
    existing_rating = await get_rating_for_request(request_id)
    if existing_rating:
        return {
            'can_rate': False,
            'reason': 'You have already rated this delivery',
            'existing_rating': existing_rating
        }
    
    # Get deliverer info
    deliverer_ref = db.collection('users').document(deliverer_uid)
    deliverer_doc = deliverer_ref.get()
    deliverer_name = "Unknown"
    if deliverer_doc.exists:
        deliverer_data = deliverer_doc.to_dict()
        deliverer_name = deliverer_data.get('name') or deliverer_data.get('email', 'Unknown')
    
    return {
        'can_rate': True,
        'reason': 'You can rate this delivery',
        'deliverer_uid': deliverer_uid,
        'deliverer_name': deliverer_name
    }


async def get_user_rating_summary(user_uid: str) -> Dict:
    """
    Get summarized rating information for user profile
    Shows ratings received as a deliverer
    
    Args:
        user_uid: User UID
        
    Returns:
        dict: Summary of ratings
    """
    user_ref = db.collection('users').document(user_uid)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user_doc.to_dict()
    rating_stats = user_data.get('rating_stats', {
        'average_rating': 0.0,
        'total_ratings': 0,
        'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    })
    
    # Calculate percentage of each rating
    total = rating_stats.get('total_ratings', 0)
    distribution = rating_stats.get('rating_distribution', {})
    
    percentage_distribution = {}
    if total > 0:
        for rating, count in distribution.items():
            percentage_distribution[rating] = round((count / total) * 100, 1)
    else:
        percentage_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    
    return {
        'average_rating': rating_stats.get('average_rating', 0.0),
        'total_ratings': total,
        'rating_distribution': distribution,
        'percentage_distribution': percentage_distribution,
        'rating_badge': get_rating_badge(rating_stats.get('average_rating', 0.0))
    }


def get_rating_badge(average_rating: float) -> str:
    """
    Get badge/label based on average rating
    
    Args:
        average_rating: Average rating value
        
    Returns:
        str: Badge label
    """
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
    """
    Update an existing rating (only by the poster, within 24 hours)
    
    Args:
        rating_id: Rating ID
        user_uid: UID of user attempting to update (must be poster)
        new_rating: New rating value
        new_comment: New comment
        
    Returns:
        dict: Updated rating
    """
    if not 1 <= new_rating <= 5:
        raise HTTPException(
            status_code=400,
            detail="Rating must be between 1 and 5"
        )
    
    rating_ref = db.collection('ratings').document(rating_id)
    rating_doc = rating_ref.get()
    
    if not rating_doc.exists:
        raise HTTPException(status_code=404, detail="Rating not found")
    
    rating_data = rating_doc.to_dict()
    
    # Verify ownership
    if rating_data.get('poster_uid') != user_uid:
        raise HTTPException(
            status_code=403,
            detail="You can only update your own ratings"
        )
    
    # Check time limit (24 hours)
    created_at = rating_data.get('created_at')
    if created_at:
        hours_since_creation = (datetime.utcnow() - created_at).total_seconds() / 3600
        if hours_since_creation > 24:
            raise HTTPException(
                status_code=403,
                detail="Cannot update rating after 24 hours"
            )
    
    # Update rating
    update_data = {
        'rating': new_rating,
        'comment': new_comment,
        'updated_at': datetime.utcnow()
    }
    rating_ref.update(update_data)
    
    # Update deliverer's stats
    await update_user_rating_stats(rating_data.get('deliverer_uid'))
    
    # Get updated rating
    updated_doc = rating_ref.get()
    return updated_doc.to_dict()


async def delete_rating(rating_id: str, user_uid: str) -> Dict:
    """
    Delete a rating (only by the poster, within 24 hours)
    
    Args:
        rating_id: Rating ID
        user_uid: UID of user attempting to delete
        
    Returns:
        dict: Success response
    """
    rating_ref = db.collection('ratings').document(rating_id)
    rating_doc = rating_ref.get()
    
    if not rating_doc.exists:
        raise HTTPException(status_code=404, detail="Rating not found")
    
    rating_data = rating_doc.to_dict()
    
    # Verify ownership
    if rating_data.get('poster_uid') != user_uid:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own ratings"
        )
    
    # Check time limit (24 hours)
    created_at = rating_data.get('created_at')
    if created_at:
        hours_since_creation = (datetime.utcnow() - created_at).total_seconds() / 3600
        if hours_since_creation > 24:
            raise HTTPException(
                status_code=403,
                detail="Cannot delete rating after 24 hours"
            )
    
    # Delete rating
    deliverer_uid = rating_data.get('deliverer_uid')
    rating_ref.delete()
    
    # Update deliverer's stats
    await update_user_rating_stats(deliverer_uid)
    
    return {
        'success': True,
        'message': 'Rating deleted successfully'
    }


async def get_ratings_given_by_user(user_uid: str) -> List[Dict]:
    """
    Get all ratings given by a user (as a poster)
    
    Args:
        user_uid: UID of poster
        
    Returns:
        list: Ratings given by this user
    """
    ratings_ref = db.collection('ratings')
    query = ratings_ref.where(
        filter=firestore.FieldFilter('poster_uid', '==', user_uid)
    ).order_by('created_at', direction=firestore.Query.DESCENDING)
    
    ratings = []
    for doc in query.stream():
        rating_data = doc.to_dict()
        
        # Get deliverer's name
        deliverer_ref = db.collection('users').document(rating_data['deliverer_uid'])
        deliverer_doc = deliverer_ref.get()
        deliverer_name = "Unknown"
        if deliverer_doc.exists:
            deliverer_data = deliverer_doc.to_dict()
            deliverer_name = deliverer_data.get('name') or deliverer_data.get('email', 'Unknown')
        
        ratings.append({
            'rating_id': rating_data.get('rating_id'),
            'request_id': rating_data.get('request_id'),
            'rating': rating_data.get('rating'),
            'comment': rating_data.get('comment'),
            'deliverer_name': deliverer_name,
            'created_at': rating_data.get('created_at')
        })
    
    return ratings