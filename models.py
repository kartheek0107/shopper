from pydantic import BaseModel, Field, field_validator, EmailStr
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
# CONNECTIVITY MODELS (UPDATED WITH DEVICE_ID)
# ============================================

class UpdateConnectivityModel(BaseModel):
    """Model for updating connectivity status with device tracking"""
    is_connected: bool = Field(..., description="Internet connectivity status")
    location_permission_granted: bool = Field(..., description="Location permission status")
    device_id: Optional[str] = Field(
        None,
        description="Unique device identifier (Android ID, IDFV, or app-generated UUID)",
        min_length=1,
        max_length=255
    )
    device_info: Optional[dict] = Field(
        None,
        description="Optional device metadata (OS, model, app version)"
    )

    @field_validator('device_id')
    @classmethod
    def validate_device_id(cls, v):
        """Validate device_id format"""
        if v is not None:
            # Strip whitespace
            v = v.strip()
            if not v:
                raise ValueError('device_id cannot be empty string')
        return v


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
    """Enhanced user profile response with device tracking"""
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

    # Device tracking (NEW)
    device_id: Optional[str] = None
    device_info: Optional[dict] = None
    device_registered_at: Optional[datetime] = None

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
# REQUEST MODELS (UPDATED - AUTO-FETCH FROM PROFILE)
# ============================================

class CreateRequestModel(BaseModel):
    """
    Model for creating a new request with area support

    UPDATED: poster_name and poster_phone are AUTO-FETCHED from user profile
    No need to provide them in the request body!
    """
    item: List[str] = Field(..., min_length=1, max_length=200)
    pickup_location: str = Field(..., min_length=1, max_length=500)
    pickup_area: str = Field(..., description="Pickup area")
    drop_location: str = Field(..., min_length=1, max_length=500)
    drop_area: str = Field(..., description="Drop area")

    # NO poster_name or poster_phone here - fetched automatically!

    reward: Optional[float] = Field(None, description="Optional reward (auto-calculated if not provided)")
    item_price: float = Field(..., gt=0, description="Total item price (must be positive)")
    time_requested: Optional[datetime] = Field(None, description="When the delivery is needed (optional)")

    notes: Optional[str] = Field(None, max_length=1000, description="Additional notes")
    deadline: datetime = Field(..., description="Deadline for request completion")
    priority: bool = Field(default=False, description="Whether the request is high priority")

    @field_validator('item')
    @classmethod
    def validate_items(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one item must be specified')
        for item in v:
            if not item or len(item.strip()) == 0:
                raise ValueError('Items cannot be empty')
            if len(item) > 200:
                raise ValueError('Each item must be less than 200 characters')
        return v

    @field_validator('reward')
    @classmethod
    def validate_reward(cls, v):
        if v is not None and v <= 0:
            raise ValueError('reward must be positive if provided')
        return v

    @field_validator('time_requested')
    @classmethod
    def time_must_be_future(cls, v):
        if v is None:
            return v

        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= now:
            raise ValueError('time_requested must be in the future')
        return v

    @field_validator('deadline')
    @classmethod
    def deadline_must_be_future(cls, v):
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)

        if v <= now:
            raise ValueError('deadline must be in the future')

        return v


class RequestResponse(BaseModel):
    """Model for request response with area fields and poster/acceptor details"""
    request_id: str
    posted_by: str
    poster_email: str
    poster_name: str  # Auto-fetched from profile
    poster_phone: str  # Auto-fetched from profile

    item: List[str]
    pickup_location: str
    pickup_area: Optional[str] = None
    drop_location: str
    drop_area: Optional[str] = None
    time_requested: Optional[datetime] = None
    item_price: Optional[float] = None
    reward: float
    reward_auto_calculated: bool = True
    status: RequestStatus

    accepted_by: Optional[str] = None
    acceptor_email: Optional[str] = None
    acceptor_name: Optional[str] = None  # Auto-fetched from profile
    acceptor_phone: Optional[str] = None  # Auto-fetched from profile

    created_at: datetime
    notes: Optional[str] = None
    deadline: datetime
    priority: bool
    is_expired: bool = False


class AcceptRequestModel(BaseModel):
    """
    Model for accepting a request

    UPDATED: acceptor_name and acceptor_phone are AUTO-FETCHED from user profile
    No need to provide them in the request body!
    """
    request_id: str
    # NO acceptor_name or acceptor_phone here - fetched automatically!


class UpdateRequestStatusModel(BaseModel):
    """Model for updating request status"""
    request_id: str
    status: RequestStatus


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
    device_id: Optional[str] = None


class AreaCountResponse(BaseModel):
    """Count of users by area"""
    area_counts: dict = Field(..., description="Area name -> user count mapping")


class ConnectivityStatsResponse(BaseModel):
    """Overall connectivity statistics with device tracking"""
    total_users: int
    reachable_users: int
    connected_users: int
    location_granted_users: int
    reachable_percentage: float
    unique_devices: int = Field(0, description="Number of unique devices")
    multi_device_users: int = Field(0, description="Users with multiple devices")


class EnhancedDashboardResponse(BaseModel):
    """Enhanced dashboard with area stats"""
    user: dict
    stats: RequestStatsResponse
    reachable_users_by_area: dict
    active_requests: List[RequestResponse]
    nearby_requests: List[RequestResponse]


# ============================================
# RATING MODELS
# ============================================

class CreateRatingModel(BaseModel):
    """Model for creating a rating"""
    request_id: str = Field(..., description="ID of the completed request")
    rating: int = Field(..., ge=1, le=5, description="Rating value (1-5 stars)")
    comment: Optional[str] = Field(None, max_length=500, description="Optional feedback comment")


class UpdateRatingModel(BaseModel):
    """Model for updating a rating"""
    rating: int = Field(..., ge=1, le=5, description="New rating value (1-5 stars)")
    comment: Optional[str] = Field(None, max_length=500, description="Updated comment")


class RatingResponse(BaseModel):
    """Model for rating response"""
    rating_id: str
    request_id: str
    poster_uid: str
    deliverer_uid: str
    rating: int
    comment: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None


class RatingDetailResponse(BaseModel):
    """Model for detailed rating with names"""
    rating_id: str
    request_id: str
    rating: int
    comment: Optional[str]
    poster_name: str
    item_delivered: str
    created_at: datetime


class RatingStatsResponse(BaseModel):
    """Model for user rating statistics"""
    average_rating: float
    total_ratings: int
    rating_distribution: dict[int, int]
    percentage_distribution: Optional[dict[int, float]] = None
    rating_badge: Optional[str] = None


class UserRatingsResponse(BaseModel):
    """Model for user's received ratings"""
    stats: RatingStatsResponse
    ratings: List[dict]


class CanRateResponse(BaseModel):
    """Model for checking if user can rate"""
    can_rate: bool
    reason: str
    deliverer_uid: Optional[str] = None
    deliverer_name: Optional[str] = None
    existing_rating: Optional[dict] = None


class RatingsGivenResponse(BaseModel):
    """Model for ratings given by user"""
    ratings: List[dict]
    total: int


# ============================================
# LOCATION MODELS (GPS Support)
# ============================================  
class GPSCoordinates(BaseModel):
    """GPS coordinates model"""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, description="Accuracy in meters")