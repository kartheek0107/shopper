from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
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
    """Model for creating a new request"""
    item: str = Field(..., min_length=1, max_length=200)
    pickup_location: str = Field(..., min_length=1, max_length=500)
    drop_location: str = Field(..., min_length=1, max_length=500)
    reward: float = Field(..., gt=0, description="Reward amount (must be positive)")
    time_requested: datetime = Field(..., description="When the delivery is needed")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional notes")
    
    @field_validator('time_requested')
    @classmethod
    def time_must_be_future(cls, v):
        # Make both datetimes timezone-aware for comparison
        now = datetime.now(timezone.utc)
        
        # If v is naive, make it aware (assume UTC)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        
        if v <= now:
            raise ValueError('time_requested must be in the future')
        return v


class RequestResponse(BaseModel):
    """Model for request response"""
    request_id: str
    posted_by: str
    poster_email: str
    item: str
    pickup_location: str
    drop_location: str
    time_requested: datetime
    reward: float
    status: RequestStatus
    accepted_by: Optional[str] = None
    acceptor_email: Optional[str] = None
    created_at: datetime
    notes: Optional[str] = None


class AcceptRequestModel(BaseModel):
    """Model for accepting a request"""
    request_id: str


class UpdateRequestStatusModel(BaseModel):
    """Model for updating request status"""
    request_id: str
    status: RequestStatus


# ============================================
# USER MODELS
# ============================================

class ToggleReachableModel(BaseModel):
    """Model for toggling user reachability"""
    reachable: bool


class UserProfileResponse(BaseModel):
    """Model for user profile response"""
    uid: str
    email: str
    name: Optional[str] = None
    email_verified: bool
    reachable: bool = False
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