# scheduler.py
import asyncio
import logging
from firestore_async import utcnow
from database import mark_expired_requests
from config import settings

logger = logging.getLogger(__name__)


async def cleanup_expired_requests_job():
    """
    Run periodically to mark expired requests.
    Interval is controlled by settings.CLEANUP_INTERVAL_MINUTES.
    Includes exponential backoff on repeated failures.
    """
    interval_seconds = settings.CLEANUP_INTERVAL_MINUTES * 60
    consecutive_errors = 0
    MAX_BACKOFF = 300  # 5 minute max backoff

    while True:
        try:
            expired_count = await mark_expired_requests()
            consecutive_errors = 0  # Reset on success
            if expired_count > 0:
                logger.info(f"✅ Marked {expired_count} requests as expired")
        except Exception as e:
            consecutive_errors += 1
            backoff = min(2 ** consecutive_errors, MAX_BACKOFF)
            logger.error(
                f"❌ Error in cleanup job (attempt {consecutive_errors}): {e}. "
                f"Backing off {backoff}s"
            )
            await asyncio.sleep(backoff)
            continue

        await asyncio.sleep(interval_seconds)