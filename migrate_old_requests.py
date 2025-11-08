"""
Migration Script: Add item_price to Old Requests
Run this once to add missing item_price field to old requests
"""

import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate("firebase-credentials.json")
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)

db = firestore.client()

def migrate_item_price():
    """
    Add item_price to old requests that don't have it.
    
    Strategy:
    - If reward exists and < 50: set item_price = reward * 5
    - If reward exists and >= 50: set item_price = reward * 3
    - If no reward: set item_price = 100.0 (default)
    """
    requests_ref = db.collection('requests')
    
    updated_count = 0
    skipped_count = 0
    
    print("Starting item_price migration...")
    print("-" * 50)
    
    for doc in requests_ref.stream():
        try:
            request_data = doc.to_dict()
            request_id = doc.id
            
            # Skip if item_price already exists
            if 'item_price' in request_data:
                skipped_count += 1
                continue
            
            # Calculate item_price based on reward
            reward = request_data.get('reward', 0)
            
            if reward < 50:
                # Small reward -> estimate item_price as 5x reward
                item_price = reward * 5
            elif reward >= 50:
                # Large reward -> estimate item_price as 3x reward
                item_price = reward * 3
            else:
                # No reward -> default
                item_price = 100.0
            
            # Ensure minimum item_price
            if item_price < 10:
                item_price = 50.0
            
            print(f"✓ Request {request_id[:8]}... reward={reward} -> item_price={item_price}")
            
            # Update document
            doc.reference.update({'item_price': item_price})
            updated_count += 1
            
        except Exception as e:
            print(f"✗ Error updating request {doc.id}: {str(e)}")
    
    print("-" * 50)
    print(f"Migration complete!")
    print(f"✅ Updated: {updated_count} requests")
    print(f"⏭️  Skipped: {skipped_count} requests (already had item_price)")

def verify_migration():
    """Verify all requests have item_price"""
    print("\nVerifying migration...")
    print("-" * 50)
    
    requests_ref = db.collection('requests')
    
    total = 0
    with_price = 0
    missing_price = []
    
    for doc in requests_ref.stream():
        total += 1
        request_data = doc.to_dict()
        
        if 'item_price' in request_data:
            with_price += 1
        else:
            missing_price.append(doc.id)
    
    print(f"Total requests: {total}")
    print(f"✅ With item_price: {with_price}")
    print(f"✗ Missing item_price: {len(missing_price)}")
    
    if missing_price:
        print("\nRequests still missing item_price:")
        for req_id in missing_price:
            print(f"  - {req_id}")
    else:
        print("\n🎉 All requests have item_price!")

if __name__ == "__main__":
    print("=" * 50)
    print("ITEM PRICE MIGRATION")
    print("=" * 50)
    print()
    
    # Run migration
    migrate_item_price()
    
    # Verify results
    verify_migration()
    
    print()
    print("=" * 50)
    print("Migration completed!")
    print("=" * 50)