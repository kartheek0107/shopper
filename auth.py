import firebase_admin
from firebase_admin import credentials, auth, firestore
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings
from firestore_async import get_db, utcnow, get_doc, update_doc, set_doc

# Initialize Firebase Admin SDK
cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)

# Security scheme for bearer token
security = HTTPBearer()


def verify_email_domain(email: str) -> bool:
    """
    Verify that the email belongs to the allowed college domain.
    
    Args:
        email: User's email address
        
    Returns:
        bool: True if email domain is allowed, False otherwise
    """
    return email.endswith(settings.ALLOWED_EMAIL_DOMAIN)


async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Verify Firebase ID token and return user information.
    This function will be used as a dependency in protected routes.
    
    Args:
        credentials: Bearer token from Authorization header
        
    Returns:
        dict: User information including uid, email, and email_verified status
        
    Raises:
        HTTPException: If token is invalid or email domain is not allowed
    """
    token = credentials.credentials
    
    try:
        # Verify the Firebase ID token
        decoded_token = auth.verify_id_token(token)
        
        # Extract user information
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        email_verified = decoded_token.get('email_verified', False)
        
        # Check if email exists
        if not email:
            raise HTTPException(
                status_code=400,
                detail="Email not found in token"
            )
        
        # Verify email domain
        if not verify_email_domain(email):
            raise HTTPException(
                status_code=403,
                detail=f"Only {settings.ALLOWED_EMAIL_DOMAIN} emails are allowed"
            )
        
        # Check if email is verified
        if not email_verified:
            raise HTTPException(
                status_code=403,
                detail="Email not verified. Please verify your email first."
            )
        
        return {
            "uid": uid,
            "email": email,
            "email_verified": email_verified
        }
        
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Authentication token has expired"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )


async def store_user_in_firestore(user_data: dict) -> dict:
    """
    Store or update user data in Firestore.

    Throttles last_login writes: skips the update if the user was seen
    less than 5 minutes ago (saves ~10K Firestore writes/min at scale).
    
    Args:
        user_data: Dictionary containing user information
        
    Returns:
        dict: Stored user data with timestamp
    """
    now = utcnow()

    user_document = {
        "uid": user_data['uid'],
        "email": user_data['email'],
        "email_verified": user_data['email_verified'],
        "last_login": now,
        "updated_at": now,
    }
    
    # Check if user already exists
    existing = await get_doc('users', user_data['uid'])
    
    if existing is not None:
        # Skip write if last_login is recent (within 5 minutes)
        last_login = existing.get('last_login')
        if last_login is not None:
            from datetime import timezone, timedelta
            if last_login.tzinfo is None:
                last_login = last_login.replace(tzinfo=timezone.utc)
            if (now - last_login) < timedelta(minutes=5):
                # User was seen recently — return existing data without writing
                return existing

        await update_doc('users', user_data['uid'], {
            "last_login": now,
            "updated_at": now,
        })
    else:
        # Create new user with created_at timestamp
        user_document["created_at"] = now
        await set_doc('users', user_data['uid'], user_document)
    
    return user_document


async def get_current_user(
    user_data: dict = Depends(verify_firebase_token)
) -> dict:
    """
    Get current authenticated user and ensure they're stored in Firestore.
    Use this as a dependency in your protected routes.
    
    Args:
        user_data: User data from token verification
        
    Returns:
        dict: Complete user information
    """
    # Store/update user in Firestore
    stored_user = await store_user_in_firestore(user_data)
    
    return stored_user