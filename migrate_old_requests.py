"""
Migration Script: Fix Old Request Data
Run this once to migrate old requests to new schema
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone, timedelta

# Initialize Firebase (adjust path if needed)
cred = credentials.Certificate("firebase-credentials.json")
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)

db = firestore.client()

def migrate_requests():
    """
    Migrate old requests to match new schema:
    1. Convert 'item' from string to list
    2. Add missing 'deadline' field
    3. Add missing 'priority' field
    4. Add missing 'is_expired' field
    """
    requests_ref = db.collection('requests')
    
    updated_count = 0
    error_count = 0
    
    print("Starting migration...")
    print("-" * 50)
    
    for doc in requests_ref.stream():
        try:
            request_data = doc.to_dict()
            request_id = doc.id
            needs_update = False
            update_data = {}
            
            # 1. Fix 'item' field (string -> list)
            item = request_data.get('item')
            if isinstance(item, str):
                print(f"✓ Request {request_id}: Converting item '{item}' to list")
                update_data['item'] = [item]
                needs_update = True
            elif item is None:
                print(f"✓ Request {request_id}: Adding empty item list")
                update_data['item'] = []
                needs_update = True
            
            # 2. Add missing 'deadline' field
            if 'deadline' not in request_data:
                # Set deadline to time_requested + 24 hours
                time_requested = request_data.get('time_requested')
                if time_requested:
                    if hasattr(time_requested, 'tzinfo') and time_requested.tzinfo is None:
                        time_requested = time_requested.replace(tzinfo=timezone.utc)
                    deadline = time_requested + timedelta(hours=24)
                else:
                    # Fallback: created_at + 24 hours
                    created_at = request_data.get('created_at', datetime.now(timezone.utc))
                    if hasattr(created_at, 'tzinfo') and created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    deadline = created_at + timedelta(hours=24)
                
                print(f"✓ Request {request_id}: Adding deadline {deadline}")
                update_data['deadline'] = deadline
                needs_update = True
            
            # 3. Add missing 'priority' field
            if 'priority' not in request_data:
                print(f"✓ Request {request_id}: Adding priority=False")
                update_data['priority'] = False
                needs_update = True
            
            # 4. Add missing 'is_expired' field
            if 'is_expired' not in request_data:
                print(f"✓ Request {request_id}: Adding is_expired=False")
                update_data['is_expired'] = False
                needs_update = True
            
            # Update the document if needed
            if needs_update:
                doc.reference.update(update_data)
                updated_count += 1
                print(f"✅ Updated request {request_id}")
                print()
            
        except Exception as e:
            error_count += 1
            print(f"❌ Error updating request {doc.id}: {str(e)}")
            print()
    
    print("-" * 50)
    print(f"Migration complete!")
    print(f"✅ Updated: {updated_count} requests")
    print(f"❌ Errors: {error_count} requests")
    print(f"Total processed: {updated_count + error_count} requests")

def verify_migration():
    """
    Verify all requests have correct schema
    """
    print("\nVerifying migration...")
    print("-" * 50)
    
    requests_ref = db.collection('requests')
    
    total = 0
    valid = 0
    issues = []
    
    for doc in requests_ref.stream():
        total += 1
        request_data = doc.to_dict()
        request_id = doc.id
        
        has_issue = False
        
        # Check item is list
        item = request_data.get('item')
        if not isinstance(item, list):
            issues.append(f"❌ {request_id}: item is not a list ({type(item).__name__})")
            has_issue = True
        
        # Check deadline exists
        if 'deadline' not in request_data:
            issues.append(f"❌ {request_id}: missing deadline")
            has_issue = True
        
        # Check priority exists
        if 'priority' not in request_data:
            issues.append(f"❌ {request_id}: missing priority")
            has_issue = True
        
        # Check is_expired exists
        if 'is_expired' not in request_data:
            issues.append(f"❌ {request_id}: missing is_expired")
            has_issue = True
        
        if not has_issue:
            valid += 1
    
    print(f"Total requests: {total}")
    print(f"✅ Valid: {valid}")
    print(f"❌ Issues: {len(issues)}")
    
    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(issue)
    else:
        print("\n🎉 All requests have correct schema!")

if __name__ == "__main__":
    print("=" * 50)
    print("REQUEST SCHEMA MIGRATION")
    print("=" * 50)
    print()
    
    # Run migration
    migrate_requests()
    
    # Verify results
    verify_migration()
    
    print()
    print("=" * 50)
    print("Migration script completed!")
    print("=" * 50)