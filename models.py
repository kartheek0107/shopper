from pydantic import BaseModel, Field, field_validator ,EmailStr
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
    item: List[str] = Field(..., min_length=1, max_length=200)
    pickup_location: str = Field(..., min_length=1, max_length=500)
    pickup_area: str = Field(..., description="Pickup area")
    drop_location: str = Field(..., min_length=1, max_length=500)
    drop_area: str = Field(..., description="Drop area")
    reward: float = Field(..., gt=0, description="Reward amount (must be positive)")
    time_requested: datetime = Field(..., description="When the delivery is needed")
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
    
    @field_validator('time_requested')
    @classmethod
    def time_must_be_future(cls, v):
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= now:
            raise ValueError('time_requested must be in the future')
        return v 
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
    item: List[str]
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



# ============================================
# RATING MODELS
# ============================================

class CreateRatingModel(BaseModel):
    """Model for creating a rating (poster rates deliverer)"""
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
    """Model for user's received ratings (as deliverer)"""
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
    """Model for ratings given by user (as poster)"""
    ratings: List[dict]
    total: int

# ============================================
# LOCATION MODELS
# ============================================  
class GPSCoordinates(BaseModel):
    """GPS coordinates model"""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, description="Accuracy in meters")


class CreateRequestModelWithGPS(BaseModel):
    """Enhanced request model with GPS coordinates"""
    item: List[str] = Field(..., min_length=1, max_length=200)
    
    # Text locations (still needed for display)
    pickup_location: str = Field(..., min_length=1, max_length=500)
    drop_location: str = Field(..., min_length=1, max_length=500)
    
    # GPS coordinates (optional but recommended)
    pickup_gps: Optional[GPSCoordinates] = Field(
        None, 
        description="GPS coordinates of pickup location"
    )
    drop_gps: Optional[GPSCoordinates] = Field(
        None, 
        description="GPS coordinates of drop location"
    )
    
    # Areas (auto-detected from GPS or manually selected)
    pickup_area: Optional[str] = Field(None, description="Pickup area")
    drop_area: Optional[str] = Field(None, description="Drop area")
    
    reward: float = Field(..., gt=0)
    time_requested: datetime
    notes: Optional[str] = Field(None, max_length=1000)
    deadline: datetime
    priority: bool = Field(default=False)


class RequestResponseWithGPS(BaseModel):
    """Enhanced request response with GPS and distance"""
    request_id: str
    posted_by: str
    poster_email: str
    item: List[str]
    
    # Text locations
    pickup_location: str
    drop_location: str
    
    # GPS coordinates
    pickup_gps: Optional[dict] = None
    drop_gps: Optional[dict] = None
    
    # Areas
    pickup_area: Optional[str] = None
    drop_area: Optional[str] = None
    
    # Calculated distance (if GPS available)
    delivery_distance_km: Optional[float] = None
    
    time_requested: datetime
    reward: float
    status: str
    accepted_by: Optional[str] = None
    acceptor_email: Optional[str] = None
    created_at: datetime
    notes: Optional[str] = None
    deadline: datetime
    priority: bool
    is_expired: bool = False
    
    # Distance from current user (if querying nearby)
    distance_from_user_km: Optional[float] = None


# Update your create_request function in database.py
# Add these imports at the top of database.py if not already there
from firebase_admin import firestore
import uuid
from datetime import datetime, timezone

db = firestore.client()

async def create_request_with_gps(user_uid: str, user_email: str, request_data: dict) -> dict:
    """
    Create request with GPS support
    Auto-detect areas if GPS provided but areas not specified
    """
    import uuid
    from datetime import datetime, timezone
    
    request_id = str(uuid.uuid4())
    
    # Auto-detect areas from GPS if not provided
    pickup_area = request_data.get("pickup_area")
    drop_area = request_data.get("drop_area")
    
    if not pickup_area and request_data.get("pickup_gps"):
        from location_service import detect_area_from_coordinates
        pickup_gps = request_data["pickup_gps"]
        pickup_area = detect_area_from_coordinates(
            pickup_gps["latitude"], 
            pickup_gps["longitude"]
        )
    
    if not drop_area and request_data.get("drop_gps"):
        from location_service import detect_area_from_coordinates
        drop_gps = request_data["drop_gps"]
        drop_area = detect_area_from_coordinates(
            drop_gps["latitude"], 
            drop_gps["longitude"]
        )
    
    # Calculate delivery distance if both GPS coordinates provided
    delivery_distance = None
    if request_data.get("pickup_gps") and request_data.get("drop_gps"):
        from location_service import calculate_distance
        pickup_gps = request_data["pickup_gps"]
        drop_gps = request_data["drop_gps"]
        delivery_distance = calculate_distance(
            pickup_gps["latitude"], pickup_gps["longitude"],
            drop_gps["latitude"], drop_gps["longitude"]
        )
    
    request_document = {
        "request_id": request_id,
        "posted_by": user_uid,
        "poster_email": user_email,
        "item": request_data["item"],
        "pickup_location": request_data["pickup_location"],
        "pickup_area": pickup_area,
        "pickup_gps": request_data.get("pickup_gps"),
        "drop_location": request_data["drop_location"],
        "drop_area": drop_area,
        "drop_gps": request_data.get("drop_gps"),
        "delivery_distance_km": delivery_distance,
        "time_requested": request_data["time_requested"],
        "reward": request_data["reward"],
        "status": "open",
        "accepted_by": None,
        "acceptor_email": None,
        "created_at": datetime.now(timezone.utc),
        "accepted_at": None,
        "completed_at": None,
        "updated_at": datetime.now(timezone.utc),
        "notes": request_data.get("notes"),
        "deadline": request_data.get("deadline"),
        "priority": request_data.get("priority", False),
        "is_expired": False,
    }
    
    # Store in Firestore
    db.collection('requests').document(request_id).set(request_document)
    
    return request_document