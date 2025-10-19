from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import EmailStr
from typing import Optional, List
from config import settings
from auth import get_current_user, verify_email_domain
from models import (
    CreateRequestModel, RequestResponse, AcceptRequestModel,
    UpdateRequestStatusModel, ToggleReachableModel, UserProfileResponse,
    UpdateProfileModel, SuccessResponse, RequestStatsResponse, RequestStatus
)
from database import (
    create_request, get_all_requests, get_user_requests, get_accepted_requests,
    get_request_by_id, accept_request, update_request_status,
    update_user_reachability, get_user_profile, update_user_profile, get_user_stats
)

# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="College Delivery Request System API"
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
        "message": "College Delivery System API - Phase 2",
        "version": settings.API_VERSION,
        "features": [
            "User Authentication",
            "Request Management",
            "Request Acceptance",
            "Status Tracking"
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
# REQUEST ENDPOINTS
# ============================================

@app.post("/request/create", response_model=RequestResponse)
async def create_request_endpoint(
    request_data: CreateRequestModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new delivery request
    
    Requires authentication. User must be verified.
    """
    try:
        request_dict = request_data.dict()
        created_request = await create_request(
            user_uid=current_user["uid"],
            user_email=current_user["email"],
            request_data=request_dict
        )
        return created_request
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/all", response_model=List[RequestResponse])
async def get_all_requests_endpoint(
    status: Optional[RequestStatus] = Query(None, description="Filter by status"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all requests, optionally filtered by status
    
    Query params:
    - status: open, accepted, completed (optional)
    """
    try:
        status_value = status.value if status else None
        requests = await get_all_requests(status=status_value)
        return requests
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/mine", response_model=List[RequestResponse])
async def get_my_requests_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all requests posted by the current user
    """
    try:
        requests = await get_user_requests(current_user["uid"])
        return requests
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/accepted", response_model=List[RequestResponse])
async def get_my_accepted_requests_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all requests accepted by the current user
    """
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
    """
    Get status and details of a specific request
    """
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
    """
    try:
        updated_request = await accept_request(
            request_id=request_data.request_id,
            user_uid=current_user["uid"],
            user_email=current_user["email"]
        )
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
    """
    try:
        updated_request = await update_request_status(
            request_id=update_data.request_id,
            new_status=update_data.status.value,
            user_uid=current_user["uid"]
        )
        return updated_request
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# USER PROFILE ENDPOINTS
# ============================================

@app.post("/user/toggle-reachable", response_model=SuccessResponse)
async def toggle_reachable_endpoint(
    data: ToggleReachableModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Toggle user's availability for accepting delivery requests
    """
    try:
        updated_user = await update_user_reachability(
            user_uid=current_user["uid"],
            reachable=data.reachable
        )
        return {
            "success": True,
            "message": f"Reachability set to {data.reachable}",
            "data": {"reachable": data.reachable}
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/user/profile")
async def get_user_profile_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Get current user's full profile"""
    profile = await get_user_profile(current_user["uid"])
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return profile


@app.put("/user/profile")
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
        return updated_profile
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
# PROTECTED DASHBOARD (Example)
# ============================================

@app.get("/protected/dashboard")
async def protected_dashboard(current_user: dict = Depends(get_current_user)):
    """Example protected endpoint - user dashboard"""
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