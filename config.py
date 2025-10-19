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
        "@iiitsonepat.ac.in"  # Change this to your college domain
    )
    
    # API configuration
    API_TITLE = "College App Backend"
    API_VERSION = "1.0.0"
    
    # CORS settings (adjust for your frontend)
    CORS_ORIGINS = [
        "http://localhost:3000",  # React default
        "http://localhost:5173",  # Vite default
    ]

settings = Settings()