"""
Redis configuration for Upstash Redis caching.
"""
from upstash_redis import Redis

# Replace these with your Upstash Redis credentials
UPSTASH_REDIS_URL = "https://composed-possum-58878.upstash.io"
UPSTASH_REDIS_TOKEN = "AeX-AAIncDFjNGRmZjliODJkZjA0ZDE3YjA2OTQ2OTg5OTg4MTRjY3AxNTg4Nzg"

# Initialize the Redis client
redis_client = Redis(url=UPSTASH_REDIS_URL, token=UPSTASH_REDIS_TOKEN)
