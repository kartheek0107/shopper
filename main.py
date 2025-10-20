from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import EmailStr
from typing import Optional, List
from config import settings
from auth import get_current_user, verify_email_domain
from models import (
    CreateRequestModel, RequestResponse, AcceptRequestModel,
    UpdateRequestStatusModel, UserProfileResponse, UpdateProfileModel,
    SuccessResponse, RequestStatsResponse, RequestStatus,
    UpdateConnectivityModel, SetPreferredAreasModel, SetCurrentAreaModel,
    RegisterFCMTokenModel, ReachabilityStatusResponse, AreaCountResponse,
    ConnectivityStatsResponse, EnhancedDashboardResponse
)
from database import (
    create_request, get_all_requests, get_user_requests, get_accepted_requests,
    get_request_by_id, accept_request, update_request_status,
    get_user_profile, update_user_profile, get_user_stats
)
from connectivity import (
    update_connectivity_status, get_reachability_status,
    get_connectivity_stats
)
from areas import (
    get_available_areas, set_user_preferred_areas, set_user_current_area,
    get_reachable_users_count, get_reachable_users_by_area,
    get_available_users, get_requests_by_area, get_nearby_requests
)
from notifications import (
    register_fcm_token, remove_fcm_token,
    send_request_accepted_notification,
    send_delivery_completed_notification,
    send_new_request_in_area_notification
)

# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# PUBLIC ENDPOINTS
# ============================================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "message": "College Delivery System API - Phase 3",
        "version": settings.API_VERSION,
        "features": [
            "User Authentication",
            "Request Management with Area Support",
            "Connectivity & Reachability Tracking",
            "Area-based Filtering",
            "Push Notifications (FCM)",
            "Real-time User Availability"
        ]
    }


@app.post("/auth/verify-email")
async def verify_email_endpoint(email: EmailStr):
    """Check if email domain is allowed before signup"""
    is_valid = verify_email_domain(email)
    
    return {
        "is_valid": is_valid,
        "message": f"Email domain is valid" if is_valid else f"Only {settings.ALLOWED_EMAIL_DOMAIN} emails allowed"
    }


# ============================================
# AUTHENTICATION ENDPOINTS
# ============================================

@app.get("/auth/me")
async def get_current_user_endpoint(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user information"""
    return {
        "uid": current_user["uid"],
        "email": current_user["email"],
        "email_verified": current_user["email_verified"],
        "message": "User authenticated successfully"
    }


# ============================================
# CONNECTIVITY ENDPOINTS (Phase 3)
# ============================================

@app.post("/user/connectivity/update", response_model=SuccessResponse)
async def update_connectivity_endpoint(
    data: UpdateConnectivityModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Update user's connectivity status and auto-compute reachability
    
    Should be called by app every 5 minutes or when connectivity changes.
    Reachability is automatically calculated as: is_connected AND location_permission_granted
    """
    try:
        updated_user = await update_connectivity_status(
            user_uid=current_user["uid"],
            is_connected=data.is_connected,
            location_permission_granted=data.location_permission_granted
        )
        
        return {
            "success": True,
            "message": "Connectivity updated successfully",
            "data": {
                "is_reachable": updated_user.get('is_reachable'),
                "is_connected": data.is_connected,
                "location_permission_granted": data.location_permission_granted
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/user/reachability/status", response_model=ReachabilityStatusResponse)
async def get_reachability_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Get current reachability status"""
    try:
        status = await get_reachability_status(current_user["uid"])
        return status
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# AREA MANAGEMENT ENDPOINTS (Phase 3)
# ============================================

@app.get("/areas/list")
async def get_areas_list(current_user: dict = Depends(get_current_user)):
    """Get list of all available campus areas"""
    return {
        "areas": get_available_areas(),
        "total": len(get_available_areas())
    }


@app.put("/user/preferred-areas", response_model=SuccessResponse)
async def set_preferred_areas_endpoint(
    data: SetPreferredAreasModel,
    current_user: dict = Depends(get_current_user)
):
    """Set user's preferred operating areas"""
    try:
        updated_user = await set_user_preferred_areas(
            user_uid=current_user["uid"],
            areas=data.preferred_areas
        )
        
        return {
            "success": True,
            "message": "Preferred areas updated successfully",
            "data": {
                "preferred_areas": updated_user.get('preferred_areas')
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/user/current-area", response_model=SuccessResponse)
async def set_current_area_endpoint(
    data: SetCurrentAreaModel,
    current_user: dict = Depends(get_current_user)
):
    """Set user's current area (optional)"""
    try:
        updated_user = await set_user_current_area(
            user_uid=current_user["uid"],
            area=data.current_area
        )
        
        return {
            "success": True,
            "message": "Current area updated successfully",
            "data": {
                "current_area": updated_user.get('current_area')
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# REACHABLE USERS COUNT (Phase 3)
# ============================================

@app.get("/users/reachable-count")
async def get_reachable_count_endpoint(
    area: Optional[str] = Query(None, description="Filter by specific area"),
    current_user: dict = Depends(get_current_user)
):
    """Get count of reachable users, optionally filtered by area"""
    try:
        count = await get_reachable_users_count(area=area)
        return {
            "count": count,
            "area": area or "all",
            "message": f"{count} reachable users" + (f" in {area}" if area else "")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/users/reachable-by-area", response_model=AreaCountResponse)
async def get_reachable_by_area_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Get count of reachable users grouped by all areas"""
    try:
        area_counts = await get_reachable_users_by_area()
        return {"area_counts": area_counts}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/users/available")
async def get_available_users_endpoint(
    area: Optional[str] = Query(None, description="Filter by specific area"),
    preferred_areas: bool = Query(False, description="Only users with preferred areas"),
    current_user: dict = Depends(get_current_user)
):
    """Get list of available (reachable) users with filters"""
    try:
        users = await get_available_users(
            area=area,
            preferred_areas_only=preferred_areas
        )
        return {
            "users": users,
            "total": len(users)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# REQUEST ENDPOINTS (Enhanced for Phase 3)
# ============================================

@app.post("/request/create", response_model=RequestResponse)
async def create_request_endpoint(
    request_data: CreateRequestModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new delivery request with area support
    
    Requires authentication. User must be verified.
    Optional: Sends notifications to users in the pickup area.
    """
    try:
        request_dict = request_data.dict()
        created_request = await create_request(
            user_uid=current_user["uid"],
            user_email=current_user["email"],
            request_data=request_dict
        )
        
        # Send notifications to users in the area (optional)
        if settings.SEND_NEW_REQUEST_NOTIFICATIONS and created_request.get('pickup_area'):
            try:
                await send_new_request_in_area_notification(
                    area=created_request['pickup_area'],
                    item=created_request['item'],
                    request_id=created_request['request_id'],
                    exclude_uid=current_user["uid"]
                )
            except Exception as e:
                # Log but don't fail the request creation
                print(f"Failed to send notifications: {e}")
        
        return created_request
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/all", response_model=List[RequestResponse])
async def get_all_requests_endpoint(
    status: Optional[RequestStatus] = Query(None, description="Filter by status"),
    pickup_area: Optional[str] = Query(None, description="Filter by pickup area"),
    drop_area: Optional[str] = Query(None, description="Filter by drop area"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all requests with optional filters
    
    Query params:
    - status: open, accepted, completed, cancelled (optional)
    - pickup_area: Filter by pickup area (optional)
    - drop_area: Filter by drop area (optional)
    """
    try:
        status_value = status.value if status else None
        requests = await get_all_requests(
            status=status_value,
            pickup_area=pickup_area,
            drop_area=drop_area
        )
        return requests
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/nearby", response_model=List[RequestResponse])
async def get_nearby_requests_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get requests near user's current or preferred areas
    
    Returns open requests where pickup or drop area matches user's areas.
    Excludes user's own requests.
    """
    try:
        requests = await get_nearby_requests(current_user["uid"])
        return requests
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/mine", response_model=List[RequestResponse])
async def get_my_requests_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Get all requests posted by the current user"""
    try:
        requests = await get_user_requests(current_user["uid"])
        return requests
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/accepted", response_model=List[RequestResponse])
async def get_my_accepted_requests_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Get all requests accepted by the current user"""
    try:
        requests = await get_accepted_requests(current_user["uid"])
        return requests
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/status/{request_id}", response_model=RequestResponse)
async def get_request_status_endpoint(
    request_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get status and details of a specific request"""
    request = await get_request_by_id(request_id)
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return request


@app.post("/request/accept", response_model=RequestResponse)
async def accept_request_endpoint(
    request_data: AcceptRequestModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Accept an open request
    
    Only one user can accept a request (atomic operation).
    Users cannot accept their own requests.
    Sends notification to the poster.
    """
    try:
        updated_request = await accept_request(
            request_id=request_data.request_id,
            user_uid=current_user["uid"],
            user_email=current_user["email"]
        )
        
        # Send notification to poster
        try:
            await send_request_accepted_notification(
                poster_uid=updated_request['posted_by'],
                acceptor_email=current_user["email"],
                item=updated_request['item'],
                request_id=updated_request['request_id']
            )
        except Exception as e:
            print(f"Failed to send notification: {e}")
        
        return updated_request
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/request/update-status", response_model=RequestResponse)
async def update_request_status_endpoint(
    update_data: UpdateRequestStatusModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Update request status
    
    Only the request poster or acceptor can update status.
    Valid transitions:
    - open -> accepted, cancelled
    - accepted -> completed, cancelled
    
    Sends notification when completed.
    """
    try:
        updated_request = await update_request_status(
            request_id=update_data.request_id,
            new_status=update_data.status.value,
            user_uid=current_user["uid"]
        )
        
        # Send notification if completed
        if update_data.status.value == 'completed':
            try:
                await send_delivery_completed_notification(
                    poster_uid=updated_request['posted_by'],
                    deliverer_email=updated_request.get('acceptor_email', 'Unknown'),
                    item=updated_request['item'],
                    request_id=updated_request['request_id']
                )
            except Exception as e:
                print(f"Failed to send notification: {e}")
        
        return updated_request
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# NOTIFICATION ENDPOINTS (Phase 3)
# ============================================

@app.post("/notifications/register", response_model=SuccessResponse)
async def register_fcm_token_endpoint(
    data: RegisterFCMTokenModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Register FCM token for push notifications
    
    Should be called when app starts and token is available.
    """
    try:
        result = await register_fcm_token(
            user_uid=current_user["uid"],
            fcm_token=data.fcm_token
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/notifications/unregister", response_model=SuccessResponse)
async def unregister_fcm_token_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Remove FCM token (on logout)
    """
    try:
        result = await remove_fcm_token(current_user["uid"])
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# USER PROFILE ENDPOINTS (Enhanced)
# ============================================

@app.get("/user/profile")
async def get_user_profile_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Get current user's full profile with all Phase 3 fields"""
    profile = await get_user_profile(current_user["uid"])
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return profile


@app.put("/user/profile", response_model=SuccessResponse)
async def update_user_profile_endpoint(
    profile_data: UpdateProfileModel,
    current_user: dict = Depends(get_current_user)
):
    """Update user profile (name, phone, etc.)"""
    try:
        # Filter out None values
        update_dict = {k: v for k, v in profile_data.dict().items() if v is not None}
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="No data to update")
        
        updated_profile = await update_user_profile(
            user_uid=current_user["uid"],
            profile_data=update_dict
        )
        return {
            "success": True,
            "message": "Profile updated successfully",
            "data": updated_profile
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/user/stats", response_model=RequestStatsResponse)
async def get_user_stats_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Get user statistics (requests posted, accepted, completed)"""
    try:
        stats = await get_user_stats(current_user["uid"])
        return stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# ENHANCED DASHBOARD (Phase 3)
# ============================================

@app.get("/dashboard/enhanced")
async def enhanced_dashboard_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Enhanced dashboard with area-based stats
    
    Returns:
    - User profile with reachability
    - Request statistics
    - Reachable users by area
    - Active requests
    - Nearby requests
    """
    try:
        # Get user profile
        user_profile = await get_user_profile(current_user["uid"])
        
        # Get user stats
        stats = await get_user_stats(current_user["uid"])
        
        # Get reachable users by area
        reachable_by_area = await get_reachable_users_by_area()
        
        # Get user's active requests
        active_requests = await get_user_requests(current_user["uid"])
        active_requests = [r for r in active_requests if r.get('status') == 'open'][:5]
        
        # Get nearby requests
        nearby_requests = await get_nearby_requests(current_user["uid"])
        nearby_requests = nearby_requests[:10]  # Limit to 10
        
        return {
            "user": user_profile,
            "stats": stats,
            "reachable_users_by_area": reachable_by_area,
            "active_requests": active_requests,
            "nearby_requests": nearby_requests
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/dashboard")
async def dashboard_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Basic dashboard - user statistics and recent activity
    """
    try:
        # Get user stats
        stats = await get_user_stats(current_user["uid"])
        
        # Get recent requests
        my_requests = await get_user_requests(current_user["uid"])
        accepted_requests = await get_accepted_requests(current_user["uid"])
        
        return {
            "message": f"Welcome, {current_user['email']}!",
            "user_id": current_user["uid"],
            "stats": stats,
            "recent_posted": my_requests[:5],  # Last 5
            "recent_accepted": accepted_requests[:5]  # Last 5
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# ADMIN/STATS ENDPOINTS (Optional)
# ============================================

@app.get("/admin/connectivity-stats", response_model=ConnectivityStatsResponse)
async def get_connectivity_stats_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get overall connectivity statistics
    
    Note: In production, this should be admin-only
    """
    try:
        stats = await get_connectivity_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# RUN SERVER
# ============================================

if __name__ == "__main__":
    import uvicorn
    import sys
    
    if sys.platform == "win32":
        import multiprocessing
        multiprocessing.freeze_support()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )