from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum


class RequestStatus(str, Enum):
    """Request status enum"""
    OPEN = "open"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ============================================
# REQUEST MODELS
# ============================================

class CreateRequestModel(BaseModel):
    """Model for creating a new request with area support"""
    item: str = Field(..., min_length=1, max_length=200)
    pickup_location: str = Field(..., min_length=1, max_length=500)
    pickup_area: str = Field(..., description="Pickup area (A, B, C, Library, etc.)")
    drop_location: str = Field(..., min_length=1, max_length=500)
    drop_area: str = Field(..., description="Drop area (A, B, C, Library, etc.)")
    reward: float = Field(..., gt=0, description="Reward amount (must be positive)")
    time_requested: datetime = Field(..., description="When the delivery is needed")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional notes")
    deadline: datetime = Field(..., description="Deadline for request completion")
    priority: bool = Field(default=False, description="Whether the request is high priority")
    
    @field_validator('time_requested')
    @classmethod
    def time_must_be_future(cls, v):
        now = datetime.now(timezone.utc)
        return now
    @field_validator('deadline')
    @classmethod
    def deadline_must_be_future_and_reasonable(cls, v, info):
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        
        # Must be in future
        if v <= now:
            raise ValueError('deadline must be in the future')
        
        # Optional: Check deadline is after time_requested
        time_requested = info.data.get('time_requested')
        if time_requested and v < time_requested:
            raise ValueError('deadline must be after time_requested')
        
        return v


class RequestResponse(BaseModel):
    """Model for request response with area fields"""
    request_id: str
    posted_by: str
    poster_email: str
    item: str
    pickup_location: str
    pickup_area: Optional[str] = None
    drop_location: str
    drop_area: Optional[str] = None
    time_requested: datetime
    reward: float
    status: RequestStatus
    accepted_by: Optional[str] = None
    acceptor_email: Optional[str] = None
    created_at: datetime
    notes: Optional[str] = None
    deadline: datetime
    priority: bool 
    is_expired: bool = False


class AcceptRequestModel(BaseModel):
    """Model for accepting a request"""
    request_id: str


class UpdateRequestStatusModel(BaseModel):
    """Model for updating request status"""
    request_id: str
    status: RequestStatus


# ============================================
# USER MODELS (Phase 3)
# ============================================

class UpdateConnectivityModel(BaseModel):
    """Model for updating connectivity status"""
    is_connected: bool = Field(..., description="Internet connectivity status")
    location_permission_granted: bool = Field(..., description="Location permission status")


class SetPreferredAreasModel(BaseModel):
    """Model for setting preferred areas"""
    preferred_areas: List[str] = Field(
        ..., 
        min_length=1,
        description="List of preferred operating areas"
    )


class SetCurrentAreaModel(BaseModel):
    """Model for setting current area"""
    current_area: Optional[str] = Field(None, description="Current area (null to clear)")


class RegisterFCMTokenModel(BaseModel):
    """Model for registering FCM token"""
    fcm_token: str = Field(..., min_length=1, description="Firebase Cloud Messaging token")


class UserProfileResponse(BaseModel):
    """Enhanced user profile response"""
    uid: str
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    email_verified: bool
    
    # Area preferences
    preferred_areas: Optional[List[str]] = []
    current_area: Optional[str] = None
    
    # Connectivity & Reachability
    is_reachable: bool = False
    is_connected: bool = False
    location_permission_granted: bool = False
    last_connectivity_check: Optional[datetime] = None
    
    # FCM
    fcm_token: Optional[str] = None
    
    # Timestamps
    created_at: datetime
    last_login: datetime


class UpdateProfileModel(BaseModel):
    """Model for updating user profile"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)


# ============================================
# RESPONSE MODELS
# ============================================

class SuccessResponse(BaseModel):
    """Generic success response"""
    success: bool = True
    message: str
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Generic error response"""
    success: bool = False
    error: str
    detail: Optional[str] = None


class RequestStatsResponse(BaseModel):
    """Statistics about requests"""
    total_posted: int
    total_accepted: int
    total_completed: int
    active_requests: int


class ReachabilityStatusResponse(BaseModel):
    """Reachability status response"""
    is_reachable: bool
    is_connected: bool
    location_permission_granted: bool
    last_connectivity_check: Optional[datetime]
    message: str


class AreaCountResponse(BaseModel):
    """Count of users by area"""
    area_counts: dict = Field(..., description="Area name -> user count mapping")


class ConnectivityStatsResponse(BaseModel):
    """Overall connectivity statistics"""
    total_users: int
    reachable_users: int
    connected_users: int
    location_granted_users: int
    reachable_percentage: float


class EnhancedDashboardResponse(BaseModel):
    """Enhanced dashboard with area stats"""
    user: dict
    stats: RequestStatsResponse
    reachable_users_by_area: dict
    active_requests: List[RequestResponse]
    nearby_requests: List[RequestResponse]