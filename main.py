from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
from config import settings
from auth import get_current_user, verify_email_domain

# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for request/response
class VerifyEmailRequest(BaseModel):
    email: EmailStr


class VerifyEmailResponse(BaseModel):
    is_valid: bool
    message: str


class UserResponse(BaseModel):
    uid: str
    email: str
    email_verified: bool
    message: str

class TokenRequest(BaseModel):
    token: str


# ============================================
# PUBLIC ENDPOINTS (No authentication required)
# ============================================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "message": "College App Backend API",
        "version": settings.API_VERSION
    }


@app.post("/auth/verify-email", response_model=VerifyEmailResponse)
async def verify_email_endpoint(request: VerifyEmailRequest):
    """
    Check if an email domain is allowed before user signs up.
    This endpoint doesn't require authentication.
    """
    is_valid = verify_email_domain(request.email)
    
    if is_valid:
        return {
            "is_valid": True,
            "message": f"Email domain is valid. You can sign up with {request.email}"
        }
    else:
        return {
            "is_valid": False,
            "message": f"Only {settings.ALLOWED_EMAIL_DOMAIN} emails are allowed"
        }


# ============================================
# PROTECTED ENDPOINTS (Authentication required)
# ============================================

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user information.
    This endpoint requires a valid Firebase ID token in the Authorization header.
    
    Header format: Authorization: Bearer <firebase_id_token>
    """
    return {
        "uid": current_user["uid"],
        "email": current_user["email"],
        "email_verified": current_user["email_verified"],
        "message": "User authenticated successfully"
    }


@app.get("/protected/dashboard")
async def protected_dashboard(current_user: dict = Depends(get_current_user)):
    """
    Example of a protected endpoint.
    Only authenticated users can access this.
    """
    return {
        "message": f"Welcome to your dashboard, {current_user['email']}!",
        "user_id": current_user["uid"],
        "access_level": "verified_student"
    }

@app.post("/auth/verify")
async def verify_token_endpoint(request: TokenRequest):
    """
    Verify Firebase token sent in request body (for app integration).
    Alternative to /auth/me which uses Authorization header.
    """
    from fastapi.security import HTTPAuthorizationCredentials
    from auth import verify_firebase_token, store_user_in_firestore
    
    try:
        # Create credentials object manually
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=request.token
        )
        
        # Verify token
        user_data = await verify_firebase_token(credentials)
        
        # Store in Firestore
        stored_user = await store_user_in_firestore(user_data)
        
        return {
            "success": True,
            "userId": stored_user["uid"],
            "email": stored_user["email"]
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


# ============================================
# EXAMPLE: Future endpoints structure
# ============================================

@app.get("/api/posts")
async def get_posts(current_user: dict = Depends(get_current_user)):
    """
    Example endpoint - get posts (requires authentication)
    """
    return {
        "message": "Posts retrieved successfully",
        "user": current_user["email"],
        "posts": []  # Add your logic here
    }


@app.post("/api/posts")
async def create_post(current_user: dict = Depends(get_current_user)):
    """
    Example endpoint - create post (requires authentication)
    """
    return {
        "message": "Post created successfully",
        "author": current_user["email"]
    }


# Run the app
if __name__ == "__main__":
    import uvicorn
    import sys
    
    # Fix for Windows + Python 3.13 multiprocessing issue
    if sys.platform == "win32":
        import multiprocessing
        multiprocessing.freeze_support()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False  # Disable auto-reload to avoid Windows multiprocessing issues
    )