import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Firebase configuration
    FIREBASE_CREDENTIALS_PATH = os.getenv(
        "FIREBASE_CREDENTIALS_PATH", 
        "firebase-credentials.json"
    )
    
    # College domain verification
    ALLOWED_EMAIL_DOMAIN = os.getenv(
        "ALLOWED_EMAIL_DOMAIN", 
        "@iiitsonepat.ac.in"
    )
    
    # API configuration
    API_TITLE = "College Delivery System API"
    API_VERSION = "3.0.0"
    API_DESCRIPTION = """
    College Delivery System API - Phase 3
    
    Features:
    - User Authentication with Firebase
    - Request Management with Area Support
    - Connectivity & Reachability Tracking
    - Area-based Filtering
    - Push Notifications (FCM)
    - Real-time User Availability
    """
    
    # CORS settings (adjust for your frontend)
    CORS_ORIGINS = [
        "http://localhost:3000",  # React default
        "http://localhost:5173",  # Vite default
        "http://localhost:8080",  # Vue default
    ]
    
    # Predefined campus areas
    CAMPUS_AREAS = [
        "A",
        "B",
        "C",
        "D",
        "Library",
        "Canteen",
        "Sports Complex",
        "Academic Block",
        "Main Gate"
    ]
    
    MIN_DEADLINE_HOURS = 1  # Minimum: 1 hour from now
    MAX_DEADLINE_HOURS = 72  # Maximum: 3 days
    DEFAULT_DEADLINE_HOURS = 24  # Default: 24 hours
    
    # Background job settings
    CLEANUP_INTERVAL_MINUTES = 0.17  # Every 10 seconds

    # Connectivity settings
    CONNECTIVITY_CHECK_INTERVAL_MINUTES = 5
    STALE_CONNECTIVITY_THRESHOLD_MINUTES = 10
    
    # Notification settings
    SEND_NEW_REQUEST_NOTIFICATIONS = True  # Enable/disable new request notifications

settings = Settings()