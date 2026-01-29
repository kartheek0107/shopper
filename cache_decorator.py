"""
Decorator for caching API responses using Upstash Redis.
"""
from functools import wraps
from cache_utils import set_cache, get_cache
import json


def cache_response(ttl: int = 3600):
    """
    Decorator to cache the response of a function.
    
    Args:
        ttl (int): Time-to-live for the cached response in seconds (default: 3600).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate a unique cache key based on the function name and arguments
            cache_key = f"{func.__name__}:{json.dumps(kwargs)}"
            
            # Check if the response is already cached
            cached_response = get_cache(cache_key)
            if cached_response is not None:
                print(f"Returning cached response for {func.__name__}")
                return cached_response
            
            # If not cached, execute the function
            print(f"Executing {func.__name__} and caching the response")
            response = func(*args, **kwargs)
            
            # Cache the response
            set_cache(cache_key, response, ttl=ttl)
            
            return response
        return wrapper
    return decorator
