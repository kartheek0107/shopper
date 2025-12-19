<div align="center">

🚀 Shopper

FastAPI + Firebase = Hyper-Local College Delivery Infrastructure

A production-ready backend designed for college campus delivery ecosystems, featuring real-time GPS area detection, unique device tracking, and a robust deliverer reputation system.

</div>

What is this?

Shopper is a specialized backend built to solve the "last-mile" delivery problem on college campuses. Unlike generic delivery apps, this system is optimized for:

Campus Geography: Understanding specific zones like "SBIT" or "Pallri" rather than just street addresses.

Student Availability: Tracking "reachability" based on internet connectivity and background location permissions.

Trust & Reputation: A closed-loop rating system where students verify the quality of their peers' delivery services.

Multi-Account Prevention: Tracking unique device IDs to ensure availability metrics aren't skewed by duplicate accounts.

Why build this?

Hyper-Local Context: Standard maps aren't detailed enough for dorm-to-dorm or lab-to-cafeteria deliveries.

Real-Time Reachability: We needed to know exactly who is actually available right now based on active connectivity pings.

Automated Lifecycle: Handling the "I forgot to close my request" problem through automated background cleanup of expired tasks.

What's working so far

[x] Secure Auth: Firebase integration restricted to college email domains.

[x] GPS Area Logic: Auto-detection of campus zones with 50m boundary buffers.

[x] Request Lifecycle: Full state machine (Open → Accepted → Completed).

[x] Device Tracking: Deduplication logic using unique Device IDs.

[x] Rating System: Deliverer feedback loop with average score calculation.

[x] Background Workers: Auto-expiration of stale requests via asyncio.

[ ] Dynamic Pricing: Implementation of complex reward calculators based on distance.

[ ] Live Maps: Integration with frontend for real-time deliverer tracking.

The Interesting Challenges

1. Area Boundary "Edge" Detection
How do you handle a user standing exactly on the line between two dorms?
The system uses a 50m buffer zone logic. Instead of a binary "In/Out," it identifies if a user is in a primary_area or if they are is_on_area_edge. This allows the app to show requests from both adjacent areas to that specific user.

2. Accuracy vs. Performance (Fast Mode)
Constant GPS updates can kill a phone battery and overload the server.

Normal Mode: Complete detection, edge checks, and nearby area lookups (User-initiated).

Fast Mode: 10x faster lookup using primary coordinate matching (Background pings).

3. Unique Device Deduplication
Some users might log in with multiple accounts to "claim" more visibility.
The connectivity system tracks a device_id. When calculating "Available Deliverers," the system counts Unique Devices rather than User UIDs, giving the community an honest view of actual delivery capacity.

# Backend Logic: Unique Device Counting
device_count = await get_reachable_users_count(
    area="SBIT", 
    count_by_device=True # Filters out duplicate accounts on one phone
)


4. The Automated Cleanup Job
Using FastAPI's lifespan event, the system spawns a background asyncio task that wakes up periodically to find requests past their deadline and marks them as is_expired.

Supported Operations

Category

Endpoints

Feature

Auth

/auth/verify-email

Restricted Domain Validation

Location

/location/update-gps

Area Auto-Detection

Requests

/request/create

Area-Based Posting

Tracking

/user/connectivity

Real-time Reachability

Reputation

/rating/deliverer

5-Star Feedback Loop

Analytics

/admin/connectivity-stats

Device Distribution Stats

⚙️ Quick Start

# 1. Install Dependencies
pip install -r requirements.txt

# 2. Configure .env
# Set FIREBASE_CREDENTIALS_PATH and ALLOWED_EMAIL_DOMAIN

# 3. Launch API
python main.py


🗺️ Roadmap

Phase 1: Foundation ✅

[x] Firebase Admin integration

[x] Basic CRUD for delivery requests

[x] Reachability state management

Phase 2: Location Intelligence ✅

[x] GPS to Area mapping

[x] Device tracking deduplication

[x] Edge-of-area detection logic

Phase 3: Reputation & Polish (In Progress)

[x] Rating system and badges

[x] FCM Push Notification triggers

[ ] Multi-area preference support

👨‍💻 Author

Kartheek Budime

<div align="center">

⭐ Star this repo if you find it helpful!

Made with ❤️ and FastAPI for the student community.

</div>
