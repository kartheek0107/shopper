"""
Utility functions for caching using Upstash Redis.
"""
from redis_config import redis_client
import json


def set_cache(key: str, value, ttl: int = 3600):
    """
    Set a value in the Redis cache with an optional TTL (time-to-live).
    
    Args:
        key (str): The key under which the value will be stored.
        value: The value to be cached.
        ttl (int): Time-to-live in seconds (default: 3600 seconds / 1 hour).
    """
    try:
        # Convert the value to a JSON string if it's not already a string
        if not isinstance(value, str):
            value = json.dumps(value)
        
        # Set the value in Redis with the specified TTL
        redis_client.set(key, value, ex=ttl)
        return True
    except Exception as e:
        print(f"Error setting cache for key {key}: {e}")
        return False


def get_cache(key: str):
    """
    Retrieve a value from the Redis cache.
    
    Args:
        key (str): The key for the cached value.
    
    Returns:
        The cached value if found, otherwise None.
    """
    try:
        value = redis_client.get(key)
        if value is not None:
            # Attempt to parse the value as JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    except Exception as e:
        print(f"Error getting cache for key {key}: {e}")
        return None


def delete_cache(key: str):
    """
    Delete a value from the Redis cache.
    
    Args:
        key (str): The key for the cached value to delete.
    
    Returns:
        True if the key was deleted, False otherwise.
    """
    try:
        redis_client.delete(key)
        return True
    except Exception as e:
        print(f"Error deleting cache for key {key}: {e}")
        return False
