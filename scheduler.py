# scheduler.py
import asyncio
from datetime import datetime
from database import mark_expired_requests
from config import settings

async def cleanup_expired_requests_job():
    """
    Run periodically to mark expired requests
    """
    interval_seconds = settings.CLEANUP_INTERVAL_MINUTES * 60
    
    while True:
        try:
            expired_count = await mark_expired_requests()
            if expired_count > 0:
                print(f"✅ Marked {expired_count} requests as expired")
        except Exception as e:
            print(f"❌ Error in cleanup job: {e}")
        
        
        await asyncio.sleep(interval_seconds)

# Start in background when app starts