"""
Redis Cache & Rate Limiter (Upstash)
====================================

Provides two production primitives backed by Upstash Redis (HTTP-based,
serverless, works across Gunicorn workers):

1. **Rate limiter**  — sliding-window counter via INCR + EXPIRE
2. **Cache helpers** — GET/SET with TTL for expensive Firestore queries

All operations are async and fail-open: if Redis is unreachable, requests
proceed without rate limiting / caching so the API never goes down because
of a cache issue.
"""

import json
import logging
from datetime import timedelta
from typing import Optional, Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Singleton Redis client
# ──────────────────────────────────────────────

_redis = None


def _get_redis():
    """Lazy-init the async Upstash Redis client."""
    global _redis
    if _redis is None:
        try:
            from upstash_redis.asyncio import Redis
            _redis = Redis.from_env()
            logger.info("✅ Upstash Redis connected")
        except Exception as e:
            logger.warning(f"⚠️ Upstash Redis unavailable: {e}")
            _redis = None
    return _redis


# ──────────────────────────────────────────────
# Rate Limiter
# ──────────────────────────────────────────────

async def check_rate_limit(
    key: str,
    max_requests: int = 1,
    window_seconds: int = 10,
) -> bool:
    """
    Atomic rate limiter using Redis INCR + EXPIRE.

    Raises HTTPException(429) if limit is exceeded.
    Falls back to allow-all if Redis is unreachable.
    """
    redis = _get_redis()
    if redis is None:
        return True  # fail-open

    rate_key = f"rl:{key}"

    try:
        count = await redis.incr(rate_key)

        # First request in the window — set the expiry
        if count == 1:
            await redis.expire(rate_key, window_seconds)

        if count > max_requests:
            ttl = await redis.ttl(rate_key)
            retry_after = max(ttl, 1)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        return True

    except HTTPException:
        raise  # re-raise 429
    except Exception as e:
        logger.warning(f"⚠️ Rate limit check failed (allowing request): {e}")
        return True  # fail-open


# ──────────────────────────────────────────────
# Cache Helpers
# ──────────────────────────────────────────────

async def cache_get(key: str) -> Optional[Any]:
    """
    Get a cached value (auto-deserialized from JSON).
    Returns None on miss or Redis failure.
    """
    redis = _get_redis()
    if redis is None:
        return None

    try:
        raw = await redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"⚠️ Cache get failed for {key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 30) -> bool:
    """
    Store a value in cache (auto-serialized to JSON).
    Returns False on failure.
    """
    redis = _get_redis()
    if redis is None:
        return False

    try:
        await redis.setex(key, ttl_seconds, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning(f"⚠️ Cache set failed for {key}: {e}")
        return False


async def cache_delete(key: str) -> bool:
    """Delete a cached key. Returns False on failure."""
    redis = _get_redis()
    if redis is None:
        return False

    try:
        await redis.delete(key)
        return True
    except Exception as e:
        logger.warning(f"⚠️ Cache delete failed for {key}: {e}")
        return False


async def cache_delete_pattern(prefix: str) -> int:
    """
    Delete all keys matching a prefix.
    Uses SCAN to avoid blocking — safe for production.
    Returns count of deleted keys, or 0 on failure.
    """
    redis = _get_redis()
    if redis is None:
        return 0

    try:
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=f"{prefix}*", count=100)
            if keys:
                await redis.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        return deleted
    except Exception as e:
        logger.warning(f"⚠️ Cache pattern delete failed for {prefix}*: {e}")
        return 0
