from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import EmailStr
from pydantic import BaseModel, Field
from typing import Optional, List
from firebase_admin import firestore
import math
from contextlib import asynccontextmanager
from config import settings
from auth import get_current_user, verify_email_domain
from scheduler import cleanup_expired_requests_job
from database import mark_expired_requests
import asyncio
from datetime import datetime

db = firestore.client()

from location_service import (
    update_user_location,
    get_nearby_users,
    is_user_in_area,
    detect_area_from_coordinates,
    calculate_delivery_distance,
    get_users_in_area,
    get_area_info,
    get_all_areas_info
)

from models import (
    CreateRequestModel, RequestResponse, AcceptRequestModel,
    UpdateRequestStatusModel, UserProfileResponse, UpdateProfileModel,
    SuccessResponse, RequestStatsResponse, RequestStatus,
    UpdateConnectivityModel, SetPreferredAreasModel, SetCurrentAreaModel,
    RegisterFCMTokenModel, ReachabilityStatusResponse, AreaCountResponse,
    ConnectivityStatsResponse, EnhancedDashboardResponse,
    CreateRatingModel, UpdateRatingModel, RatingResponse, 
    UserRatingsResponse, CanRateResponse, RatingStatsResponse,
    RatingsGivenResponse
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
from ratings import (
    create_rating, get_user_ratings, get_rating_for_request,
    can_rate_request, get_user_rating_summary, delete_rating,
    update_rating, get_ratings_given_by_user
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background tasks
    cleanup_task = asyncio.create_task(cleanup_expired_requests_job())
    print("✅ Started background cleanup job")
    
    yield  # Application is running
    
    # Shutdown: Cancel background tasks
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        print("🛑 Background cleanup job stopped")

# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    lifespan=lifespan
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
        "message": "College Delivery System API - Phase 3 with Device Tracking",
        "version": settings.API_VERSION,
        "features": [
            "User Authentication",
            "Request Management with Area Support",
            "Connectivity & Reachability Tracking",
            "Device Tracking & Multi-Account Detection",
            "Area-based Filtering",
            "Push Notifications (FCM)",
            "Real-time User Availability",
            "Deliverer Rating System"
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
# CONNECTIVITY ENDPOINTS (Phase 3 - UPDATED WITH DEVICE TRACKING)
# ============================================

@app.post("/user/connectivity/update", response_model=SuccessResponse)
async def update_connectivity_endpoint(
    data: UpdateConnectivityModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Update user's connectivity status and auto-compute reachability with device tracking
    
    Changes in this version:
    - Now accepts optional device_id and device_info
    - Enables accurate device counting and multi-account detection
    - Fully backward compatible (device_id is optional)
    
    Should be called by app every 5 minutes or when connectivity changes.
    Reachability is automatically calculated as: is_connected AND location_permission_granted
    
    Request Body:
    {
        "is_connected": true,
        "location_permission_granted": true,
        "device_id": "android-abc123xyz",  // Optional but recommended
        "device_info": {                   // Optional
            "os": "Android",
            "model": "Samsung Galaxy S21",
            "app_version": "1.0.5"
        }
    }
    """
    try:
        updated_user = await update_connectivity_status(
            user_uid=current_user["uid"],
            is_connected=data.is_connected,
            location_permission_granted=data.location_permission_granted,
            device_id=data.device_id,      # NEW
            device_info=data.device_info   # NEW
        )
        
        return {
            "success": True,
            "message": "Connectivity updated successfully",
            "data": {
                "is_reachable": updated_user.get('is_reachable'),
                "is_connected": data.is_connected,
                "location_permission_granted": data.location_permission_granted,
                "device_id": updated_user.get('device_id'),  # NEW
                "device_tracked": data.device_id is not None  # NEW
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/user/reachability/status", response_model=ReachabilityStatusResponse)
async def get_reachability_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current reachability status with device information
    
    Returns connectivity status plus device tracking info if available
    """
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

class UpdateGPSLocationModel(BaseModel):
    """Model for updating GPS location"""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, description="GPS accuracy in meters")
    fast_mode: bool = Field(False, description="Enable fast mode (no edge detection)")


class BulkLocationUpdate(BaseModel):
    """Model for bulk location updates (admin/testing)"""
    updates: List[dict] = Field(..., description="List of {user_uid, latitude, longitude}")


class NearbyUsersQuery(BaseModel):
    """Query for finding nearby users"""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_meters: float = Field(5000.0, gt=0, le=50000, description="Search radius in meters")


class DetectAreaModel(BaseModel):
    """Model for detecting area from coordinates"""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


# ============================================
# GPS LOCATION ENDPOINTS
# ============================================

@app.post("/location/update-gps")
async def update_gps_location_endpoint(
    location: UpdateGPSLocationModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Update user's GPS location and auto-detect area(s)
    
    Handles edge cases:
    - Users on area boundaries get flagged (normal mode)
    - Users in overlapping areas get all matching areas (normal mode)
    - 50m buffer zone for edge detection
    - Users outside all areas get assigned to nearest (within 10km)
    
    Fast mode (fast_mode=true):
    - 10x faster, only returns primary area
    - No edge detection, no nearby areas
    - Use for frequent background updates
    
    Normal mode (fast_mode=false):
    - Complete area info with edge detection
    - Use for user-initiated location updates
    
    The app should call this endpoint:
    - When user opens app: fast_mode=false (full info)
    - Background updates (every 5-10 min): fast_mode=true (fast)
    - User manually refreshes: fast_mode=false (full info)
    """
    try:
        result = await update_user_location(
            user_uid=current_user["uid"],
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy=location.accuracy,
            fast_mode=location.fast_mode
        )
        
        return {
            'success': True,
            'message': 'GPS location updated',
            'fast_mode': location.fast_mode,
            'data': result
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/location/my-gps")
async def get_my_gps_location_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Get current user's stored GPS location with area info"""
    user_ref = db.collection('users').document(current_user["uid"])
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user_doc.to_dict()
    gps_location = user_data.get('gps_location')
    
    if not gps_location:
        return {
            'has_location': False,
            'message': 'No GPS location stored'
        }
    
    return {
        'has_location': True,
        'gps_location': gps_location,
        'primary_area': user_data.get('current_area'),
        'all_matching_areas': user_data.get('all_areas', []),
        'is_on_edge': user_data.get('is_on_area_edge', False),
        'nearby_areas': user_data.get('nearby_areas', [])
    }


@app.post("/location/detect-area")
async def detect_area_endpoint(
    coords: DetectAreaModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Detect which area(s) specific coordinates belong to
    
    Useful for:
    - Testing area detection before saving
    - Validating pickup/drop locations
    - Showing area info on map
    """
    try:
        area_info = detect_area_from_coordinates(
            coords.latitude,
            coords.longitude,
            include_nearby=True
        )
        
        return {
            'success': True,
            'coordinates': {
                'latitude': coords.latitude,
                'longitude': coords.longitude
            },
            'area_info': area_info
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/location/nearby-users")
async def get_nearby_users_endpoint(
    query: NearbyUsersQuery,
    current_user: dict = Depends(get_current_user)
):
    """
    Find nearby reachable users within specified radius
    
    Useful for:
    - Finding deliverers near your location
    - Showing delivery options with actual distances
    """
    try:
        nearby = await get_nearby_users(
            latitude=query.latitude,
            longitude=query.longitude,
            radius_m=query.radius_meters
        )
        
        return {
            'total': len(nearby),
            'radius_meters': query.radius_meters,
            'radius_km': round(query.radius_meters / 1000, 2),
            'users': nearby
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/location/users-in-area/{area_name}")
async def get_users_in_area_endpoint(
    area_name: str,
    include_edge_users: bool = Query(True, description="Include users on area boundary"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all reachable users in a specific area
    
    Args:
        area_name: Area name (SBIT, Pallri, etc.)
        include_edge_users: Whether to include users on the edge (default: true)
    """
    try:
        users = await get_users_in_area(area_name, include_edge_users)
        
        return {
            'area': area_name,
            'total': len(users),
            'include_edge_users': include_edge_users,
            'users': users
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/location/nearby-requests-gps")
async def get_nearby_requests_by_gps_endpoint(
    radius_meters: float = Query(5000.0, description="Search radius in meters"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get requests near user's current GPS location
    
    More accurate than area-based filtering.
    Requires user to have GPS location stored.
    """
    # Get user's GPS location
    user_ref = db.collection('users').document(current_user["uid"])
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user_doc.to_dict()
    gps_location = user_data.get('gps_location')
    
    if not gps_location:
        raise HTTPException(
            status_code=400,
            detail="GPS location not available. Please update your location first."
        )
    
    user_lat = gps_location['latitude']
    user_lon = gps_location['longitude']
    
    # Get all open requests
    requests_ref = db.collection('requests')
    query = requests_ref.where(filter=firestore.FieldFilter('status', '==', 'open'))
    
    nearby_requests = []
    
    from location_service import calculate_distance_meters
    
    for doc in query.stream():
        request_data = doc.to_dict()
        
        # Skip own requests
        if request_data.get('posted_by') == current_user["uid"]:
            continue
        
        # Check if request has GPS coordinates for pickup
        pickup_gps = request_data.get('pickup_gps')
        if not pickup_gps:
            continue
        
        # Calculate distance from user to pickup location
        distance = calculate_distance_meters(
            user_lat, user_lon,
            pickup_gps['latitude'], pickup_gps['longitude']
        )
        
        if distance <= radius_meters:
            request_data['distance_meters'] = round(distance, 2)
            request_data['distance_km'] = round(distance / 1000, 2)
            nearby_requests.append(request_data)
    
    # Sort by distance
    nearby_requests.sort(key=lambda x: x.get('distance_meters', 999999))
    
    return {
        'total': len(nearby_requests),
        'radius_meters': radius_meters,
        'radius_km': round(radius_meters / 1000, 2),
        'user_location': {
            'latitude': user_lat,
            'longitude': user_lon
        },
        'requests': nearby_requests
    }


@app.get("/location/check-area/{area_name}")
async def check_if_in_area_endpoint(
    area_name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Check if user's current GPS location is within a specific area
    
    Useful for:
    - Verifying user is actually at pickup location
    - Confirming delivery area before accepting
    """
    try:
        result = await is_user_in_area(current_user["uid"], area_name)
        
        message = f"You are {'in' if result['is_in_area'] else 'not in'} {area_name}"
        if result['is_in_area'] and result.get('is_on_edge'):
            message += " (near boundary)"
        
        return {
            **result,
            'message': message
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/location/area-info/{area_name}")
async def get_area_info_endpoint(
    area_name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get information about a specific area (center coordinates, radius)
    
    Useful for:
    - Displaying area boundaries on map
    - Showing area coverage
    """
    info = get_area_info(area_name)
    
    if not info:
        raise HTTPException(
            status_code=404,
            detail=f"Area '{area_name}' not found"
        )
    
    return info


@app.get("/location/all-areas")
async def get_all_areas_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get information about all defined areas
    
    Useful for:
    - Displaying all areas on map
    - Showing coverage zones
    """
    areas = get_all_areas_info()
    
    return {
        'total': len(areas),
        'areas': areas
    }


@app.post("/location/bulk-update")
async def bulk_location_update_endpoint(
    updates: BulkLocationUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Bulk update locations (for testing/admin)
    Uses fast mode for efficiency
    
    Example:
    {
      "updates": [
        {"user_uid": "user1", "latitude": 28.989, "longitude": 77.150},
        {"user_uid": "user2", "latitude": 28.970, "longitude": 77.153}
      ]
    }
    """
    from location_service import detect_area_from_coordinates_fast
    
    results = []
    errors = []
    
    for update in updates.updates:
        try:
            user_uid = update.get('user_uid')
            lat = update.get('latitude')
            lon = update.get('longitude')
            
            if not user_uid or lat is None or lon is None:
                errors.append(f"Invalid update: {update}")
                continue
            
            # Use ultra-fast detection
            area = detect_area_from_coordinates_fast(lat, lon)
            
            # Update user
            user_ref = db.collection('users').document(user_uid)
            user_ref.update({
                'gps_location': {
                    'latitude': lat,
                    'longitude': lon,
                    'last_updated': datetime.utcnow()
                },
                'current_area': area,
                'updated_at': datetime.utcnow()
            })
            
            results.append({
                'user_uid': user_uid,
                'area': area,
                'success': True
            })
            
        except Exception as e:
            errors.append(f"Error for {update}: {str(e)}")
    
    return {
        'total_updates': len(updates.updates),
        'successful': len(results),
        'failed': len(errors),
        'results': results,
        'errors': errors
    }


@app.get("/location/performance-test")
async def location_performance_test(
    current_user: dict = Depends(get_current_user)
):
    """
    Test performance of different detection methods
    
    Useful for comparing fast vs normal mode
    """
    import time
    from location_service import detect_area_from_coordinates, detect_area_from_coordinates_fast
    
    # Test coordinates (SBIT area)
    test_coords = [
        (28.9890834, 77.1506293),  # SBIT center
        (28.9894, 77.1509),  # SBIT edge
        (28.9709633, 77.1531023),  # Pallri center
        (28.9845887, 77.0373188),  # Sonepat center
        (28.920, 77.100)  # Random outside
    ]
    
    # Test fast mode
    start_fast = time.time()
    fast_results = []
    for lat, lon in test_coords * 100:  # 500 iterations
        area = detect_area_from_coordinates_fast(lat, lon)
        fast_results.append(area)
    fast_time = time.time() - start_fast
    
    # Test normal mode
    start_normal = time.time()
    normal_results = []
    for lat, lon in test_coords * 100:  # 500 iterations
        info = detect_area_from_coordinates(lat, lon, include_nearby=False)
        normal_results.append(info['primary_area'])
    normal_time = time.time() - start_normal
    
    return {
        'test_iterations': len(test_coords) * 100,
        'fast_mode': {
            'time_seconds': round(fast_time, 3),
            'avg_per_lookup_ms': round((fast_time / (len(test_coords) * 100)) * 1000, 2)
        },
        'normal_mode': {
            'time_seconds': round(normal_time, 3),
            'avg_per_lookup_ms': round((normal_time / (len(test_coords) * 100)) * 1000, 2)
        },
        'speedup': f"{round(normal_time / fast_time, 1)}x faster",
        'recommendation': 'Use fast_mode=true for frequent background updates, fast_mode=false for user-initiated updates'
    }


@app.post("/location/calculate-delivery-distance")
async def calculate_delivery_distance_endpoint(
    pickup: DetectAreaModel,
    drop: DetectAreaModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Calculate distance and area info for a delivery route
    
    Useful for:
    - Estimating delivery distance before creating request
    - Showing route information
    """
    try:
        distance_info = await calculate_delivery_distance(
            pickup_location={
                'latitude': pickup.latitude,
                'longitude': pickup.longitude
            },
            drop_location={
                'latitude': drop.latitude,
                'longitude': drop.longitude
            }
        )
        
        return {
            'success': True,
            'pickup': {
                'latitude': pickup.latitude,
                'longitude': pickup.longitude,
                'area': distance_info['pickup_area']
            },
            'drop': {
                'latitude': drop.latitude,
                'longitude': drop.longitude,
                'area': distance_info['drop_area']
            },
            'distance_meters': distance_info['distance_meters'],
            'distance_km': distance_info['distance_km'],
            'crosses_areas': distance_info['crosses_areas']
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# UPDATED REACHABLE USERS COUNT WITH DEVICE TRACKING
# ============================================

@app.get("/users/reachable-count")
async def get_reachable_count_endpoint(
    area: Optional[str] = Query(None, description="Filter by specific area"),
    count_by_device: bool = Query(True, description="Count unique devices instead of users"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get count of reachable users or unique devices, optionally filtered by area
    
    NEW PARAMETER:
    - count_by_device: If true (default), counts unique devices; if false, counts users
    
    Benefits of device counting:
    - Prevents double-counting users with multiple accounts
    - More accurate availability metrics
    - Better capacity planning
    
    Examples:
    - GET /users/reachable-count?area=SBIT&count_by_device=true
      Returns: Unique devices in SBIT area
    
    - GET /users/reachable-count?count_by_device=false
      Returns: Total user count (old behavior)
    """
    try:
        count = await get_reachable_users_count(
            area=area,
            count_by_device=count_by_device
        )
        
        counting_method = "unique_devices" if count_by_device else "users"
        area_msg = f" in {area}" if area else ""
        
        return {
            "count": count,
            "counting_method": counting_method,  # NEW
            "area": area or "all",
            "message": f"{count} {counting_method} available{area_msg}"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/users/reachable-by-area", response_model=AreaCountResponse)
async def get_reachable_by_area_endpoint(
    count_by_device: bool = Query(True, description="Count unique devices per area"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get count of reachable users or devices grouped by all areas
    
    NEW PARAMETER:
    - count_by_device: If true (default), counts unique devices per area
    
    Note: When device counting is enabled, same device won't be counted 
    multiple times across different areas
    """
    try:
        area_counts = await get_reachable_users_by_area(
            count_by_device=count_by_device
        )
        
        return {
            "area_counts": area_counts,
            "counting_method": "unique_devices" if count_by_device else "users",  # NEW
            "note": "Counts represent unique devices per area" if count_by_device else "Counts represent users per area"
        }
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
# NEW DEVICE ANALYTICS ENDPOINTS
# ============================================

@app.get("/users/unique-devices")
async def get_unique_devices_endpoint(
    area: Optional[str] = Query(None, description="Filter by specific area"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get count of unique reachable devices with detailed breakdown
    
    Returns:
    - Unique device count
    - Total user count for comparison
    - Users without device_id (using fallback counting)
    
    Useful for:
    - Monitoring device adoption
    - Identifying deduplication effectiveness
    - Capacity planning
    """
    try:
        from connectivity import get_unique_reachable_devices
        
        result = await get_unique_reachable_devices(area=area)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/analytics/device-distribution")
async def get_device_distribution_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get device analytics across all areas
    
    Returns per-area breakdown:
    - Unique devices
    - Total users
    - Users without device_id
    - Device coverage percentage
    
    Useful for:
    - Understanding device adoption per area
    - Identifying areas needing mobile app updates
    - Monitoring system health
    """
    try:
        from areas import get_area_device_analytics
        
        analytics = await get_area_device_analytics()
        return {
            "area_analytics": analytics,
            "summary": {
                "total_unique_devices": sum(a['unique_devices'] for a in analytics.values()),
                "total_users": sum(a['total_users'] for a in analytics.values()),
                "overall_coverage_pct": round(
                    sum(a['unique_devices'] for a in analytics.values()) / 
                    sum(a['total_users'] for a in analytics.values()) * 100
                    if sum(a['total_users'] for a in analytics.values()) > 0 else 0,
                    2
                )
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/analytics/device-info")
async def get_device_analytics_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed device analytics including OS distribution
    
    Returns:
    - Total devices tracked
    - OS distribution (Android, iOS counts)
    - Devices with multiple accounts (edge case detection)
    
    Useful for:
    - Platform distribution insights
    - Multi-account detection
    - System monitoring
    """
    try:
        from connectivity import get_device_analytics
        
        analytics = await get_device_analytics()
        return analytics
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

@app.post("/request/cleanup-expired")
async def cleanup_expired_requests(
    current_user: dict = Depends(get_current_user)
):
    """
    Manually trigger cleanup of expired requests
    (In production, this should run as a scheduled job)
    """
    try:
        expired_count = await mark_expired_requests()
        return {
            "success": True,
            "message": f"Marked {expired_count} requests as expired"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/request/all", response_model=List[RequestResponse])
async def get_all_requests_endpoint(
    status: Optional[RequestStatus] = Query(None, description="Filter by status"),
    pickup_area: Optional[str] = Query(None, description="Filter by pickup area"),
    drop_area: Optional[str] = Query(None, description="Filter by drop area"),
    priority_only: bool = Query(False, description="Show only priority requests"),
    include_expired: bool = Query(False, description="Include expired requests"),
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
            drop_area=drop_area,
            include_expired=include_expired,
        )

        if priority_only:
            requests = [r for r in requests if r.get('priority', False)]

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
# RATING ENDPOINTS
# ============================================

@app.post("/rating/create", response_model=RatingResponse)
async def create_rating_endpoint(
    rating_data: CreateRatingModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a rating for a completed delivery
    
    Requirements:
    - User must be the request poster
    - Request must be completed
    - Poster hasn't already rated this delivery
    - Rating must be 1-5 stars
    
    Only the poster can rate the deliverer (acceptor).
    """
    try:
        rating = await create_rating(
            request_id=rating_data.request_id,
            rater_uid=current_user["uid"],
            rating=rating_data.rating,
            comment=rating_data.comment
        )
        
        return rating
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/rating/{rating_id}", response_model=RatingResponse)
async def update_rating_endpoint(
    rating_id: str,
    update_data: UpdateRatingModel,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing rating (within 24 hours)
    
    Only the poster who created the rating can update it.
    """
    try:
        updated_rating = await update_rating(
            rating_id=rating_id,
            user_uid=current_user["uid"],
            new_rating=update_data.rating,
            new_comment=update_data.comment
        )
        
        return updated_rating
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rating/deliverer/{user_uid}", response_model=UserRatingsResponse)
async def get_deliverer_ratings_endpoint(
    user_uid: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all ratings received by a user as a deliverer
    
    Returns rating statistics and individual ratings with comments.
    Useful for viewing a deliverer's reputation.
    """
    try:
        ratings = await get_user_ratings(user_uid)
        return ratings
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rating/my-deliverer-ratings", response_model=UserRatingsResponse)
async def get_my_deliverer_ratings_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all ratings you've received as a deliverer
    
    Shows your delivery performance ratings.
    """
    try:
        ratings = await get_user_ratings(current_user["uid"])
        return ratings
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rating/my-given-ratings", response_model=RatingsGivenResponse)
async def get_my_given_ratings_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all ratings you've given as a poster
    
    Shows all the deliverers you've rated.
    """
    try:
        ratings = await get_ratings_given_by_user(current_user["uid"])
        return {
            "ratings": ratings,
            "total": len(ratings)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rating/request/{request_id}")
async def get_request_rating_endpoint(
    request_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get rating for a specific request
    
    Returns the rating if it exists, useful for checking if you've already rated.
    """
    try:
        rating = await get_rating_for_request(request_id)
        
        if not rating:
            return {
                "exists": False,
                "message": "No rating found for this request"
            }
        
        return {
            "exists": True,
            "rating": rating
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rating/can-rate/{request_id}", response_model=CanRateResponse)
async def can_rate_request_endpoint(
    request_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Check if current user can rate the deliverer for a request
    
    Returns:
    - Whether rating is possible
    - Who would be rated (deliverer info)
    - Reason if cannot rate
    - Existing rating if already rated
    """
    try:
        can_rate = await can_rate_request(request_id, current_user["uid"])
        return can_rate
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rating/summary/{user_uid}", response_model=RatingStatsResponse)
async def get_deliverer_rating_summary_endpoint(
    user_uid: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get summarized rating information for a deliverer
    
    Useful for displaying in:
    - User profiles
    - Available deliverers list
    - Request acceptor cards
    """
    try:
        summary = await get_user_rating_summary(user_uid)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rating/my-summary", response_model=RatingStatsResponse)
async def get_my_rating_summary_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get your own rating summary as a deliverer
    
    Shows your delivery reputation score.
    """
    try:
        summary = await get_user_rating_summary(current_user["uid"])
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/rating/{rating_id}", response_model=SuccessResponse)
async def delete_rating_endpoint(
    rating_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a rating (within 24 hours of creation)
    
    Only the poster who created the rating can delete it.
    """
    try:
        result = await delete_rating(rating_id, current_user["uid"])
        return result
    except HTTPException:
        raise
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
    Enhanced dashboard with area-based stats and rating info
    
    Returns:
    - User profile with reachability
    - Request statistics
    - Deliverer rating summary
    - Reachable users by area
    - Active requests
    - Nearby requests
    """
    try:
        # Get user profile
        user_profile = await get_user_profile(current_user["uid"])
        
        # Get user stats
        stats = await get_user_stats(current_user["uid"])
        
        # Get deliverer rating summary
        try:
            deliverer_rating = await get_user_rating_summary(current_user["uid"])
        except:
            deliverer_rating = {
                "average_rating": 0.0,
                "total_ratings": 0,
                "rating_badge": "No Ratings Yet"
            }
        
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
            "deliverer_rating": deliverer_rating,
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
# UPDATED ADMIN/STATS ENDPOINT WITH DEVICE TRACKING
# ============================================

@app.get("/admin/connectivity-stats", response_model=ConnectivityStatsResponse)
async def get_connectivity_stats_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Get overall connectivity statistics with device tracking
    
    NEW FIELDS:
    - unique_devices: Count of unique devices
    - users_with_devices: Users who have device_id registered
    - multi_device_users: Edge case indicator (should be near 0)
    
    Note: In production, this should be admin-only
    """
    try:
        stats = await get_connectivity_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================
# HELPER ENDPOINT FOR TESTING DEVICE TRACKING
# ============================================

@app.get("/debug/device-count-comparison")
async def device_count_comparison_endpoint(
    area: Optional[str] = Query(None, description="Optional area filter"),
    current_user: dict = Depends(get_current_user)
):
    """
    Compare user-based vs device-based counting
    
    Useful for:
    - Verifying device counting works correctly
    - Understanding deduplication impact
    - Testing and debugging
    
    Returns side-by-side comparison of both counting methods
    """
    try:
        # Get counts using both methods
        user_count = await get_reachable_users_count(
            area=area, 
            count_by_device=False
        )
        
        device_count = await get_reachable_users_count(
            area=area, 
            count_by_device=True
        )
        
        deduplication_count = user_count - device_count
        
        return {
            "area": area or "all",
            "user_based_count": user_count,
            "device_based_count": device_count,
            "deduplication_impact": {
                "duplicate_accounts_detected": deduplication_count,
                "reduction_percentage": round(
                    (deduplication_count / user_count * 100) if user_count > 0 else 0,
                    2
                )
            },
            "recommendation": "Use device_based_count for accurate availability" if deduplication_count > 0 else "Both methods show same count"
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