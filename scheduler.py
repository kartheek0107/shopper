# scheduler.py
import asyncio
from datetime import datetime
from database import mark_expired_requests

async def cleanup_expired_requests_job():
    """
    Run periodically to mark expired requests
    """
    while True:
        try:
            expired_count = await mark_expired_requests()
            if expired_count > 0:
                print(f"✅ Marked {expired_count} requests as expired")
        except Exception as e:
            print(f"❌ Error in cleanup job: {e}")
        
        # Run every 10 minutes
        await asyncio.sleep(600)

# Start in background when app starts