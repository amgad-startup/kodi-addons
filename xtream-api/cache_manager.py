"""Module for managing API response caching."""

import os
import json
import time
from functools import wraps
from pathlib import Path

class CacheManager:
    def __init__(self, cache_dir="cache", cache_duration=3600):  # 1 hour default cache duration
        """Initialize the cache manager."""
        self.cache_dir = Path(cache_dir)
        self.cache_duration = cache_duration
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """Ensure the cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key):
        """Get the file path for a cache key."""
        # Create a safe filename from the cache key
        safe_key = "".join(c if c.isalnum() else "_" for c in str(key))
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key):
        """Get a value from the cache."""
        cache_path = self._get_cache_path(key)
        
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r') as f:
                cached_data = json.load(f)

            # Check if cache has expired
            if time.time() - cached_data['timestamp'] > self.cache_duration:
                os.remove(cache_path)
                return None

            return cached_data['data']
        except (json.JSONDecodeError, KeyError, OSError):
            # If there's any error reading the cache, return None
            if cache_path.exists():
                os.remove(cache_path)
            return None

    def set(self, key, value):
        """Set a value in the cache."""
        cache_path = self._get_cache_path(key)
        
        try:
            cache_data = {
                'timestamp': time.time(),
                'data': value
            }
            
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f)
        except (OSError, TypeError):
            # If there's any error writing the cache, silently fail
            if cache_path.exists():
                os.remove(cache_path)

    def clear(self):
        """Clear all cached data."""
        for cache_file in self.cache_dir.glob('*.json'):
            try:
                os.remove(cache_file)
            except OSError:
                pass

def cache_response(cache_key):
    """Decorator to cache API responses."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Generate a unique cache key based on the function name and arguments
            full_key = f"{cache_key}_{func.__name__}_{str(args)}_{str(kwargs)}"
            
            # Try to get cached response
            cached_result = self.cache_manager.get(full_key)
            if cached_result is not None:
                return cached_result

            # If no cache hit, call the original function
            result = func(self, *args, **kwargs)
            
            # Cache the result if it's valid
            if result is not None:
                self.cache_manager.set(full_key, result)
            
            return result
        return wrapper
    return decorator
