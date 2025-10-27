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
    
    # Gmail SMTP Configuration
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_EMAIL = os.getenv("SMTP_EMAIL")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "College Delivery System")
    
    # Frontend URL for verification links
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # API configuration
    API_TITLE = "College Delivery System API"
    API_VERSION = "3.0.0"
    API_DESCRIPTION = """
    College Delivery System API - Phase 3
    
    Features:
    - User Authentication with Firebase
    - Email Verification via Gmail SMTP
    - Request Management with Area Support
    - Connectivity & Reachability Tracking
    - Area-based Filtering
    - Push Notifications (FCM)
    - Real-time User Availability
    - Deliverer Rating System
    """
    
    # CORS settings (adjust for your frontend)
    CORS_ORIGINS = [
        "http://localhost:3000",  # React default
        "http://localhost:5173",  # Vite default
        "http://localhost:8080",  # Vue default
    ]
    
    # Predefined campus areas
    CAMPUS_AREAS = [
        "SBIT",
        "Pallri",
        "Bahalgarh",
        "Sonepat",
        "TDI",
        "New Delhi"
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
    
    # Email verification settings
    VERIFICATION_TOKEN_EXPIRY_HOURS = 24  # Verification link expires in 24 hours

settings = Settings()