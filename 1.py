import requests
import json

# Get these from Firebase Console → Project Settings → General
FIREBASE_API_KEY = "AIzaSyBuUSpnZFad_Vu0qxhYwjOjbZ_wU0jQs-A"  # Web API Key
FIREBASE_AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts"

def signup_user(email: str, password: str):
    """Create a new user"""
    url = f"{FIREBASE_AUTH_URL}:signUp?key={FIREBASE_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ User created: {email}")
        print(f"ID Token: {data['idToken']}\n")
        return data['idToken']
    else:
        print(f"❌ Error: {response.json()}")
        return None

def login_user(email: str, password: str):
    """Login and get ID token"""
    url = f"{FIREBASE_AUTH_URL}:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Login successful: {email}")
        print(f"ID Token: {data['idToken']}\n")
        return data['idToken']
    else:
        print(f"❌ Error: {response.json()}")
        return None

def send_verification_email(id_token: str):
    """Send email verification"""
    url = f"{FIREBASE_AUTH_URL}:sendOobCode?key={FIREBASE_API_KEY}"
    payload = {
        "requestType": "VERIFY_EMAIL",
        "idToken": id_token
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("✅ Verification email sent!")
    else:
        print(f"❌ Error sending verification: {response.json()}")

if __name__ == "__main__":
    # Test credentials
    test_email = "kartheekbudimebcs12311022@iiitsonepat.ac.in"
    test_password = "Test123456"
    
    print("🔥 Firebase Token Generator\n")
    print("1. Sign up new user")
    print("2. Login existing user")
    choice = input("\nEnter choice (1 or 2): ")
    
    if choice == "1":
        token = signup_user(test_email, test_password)
        if token:
            send_verification_email(token)
            print("\n⚠️ Note: Email needs to be verified. Check inbox or manually verify in Firebase Console.")
    elif choice == "2":
        token = login_user(test_email, test_password)
    
    if token:
        print("\n" + "="*60)
        print("Copy this token to test your API:")
        print("="*60)
        print(token)