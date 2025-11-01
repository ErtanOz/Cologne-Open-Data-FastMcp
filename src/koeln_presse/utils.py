"""Utility functions for the Köln Presse MCP server."""

import hashlib
import time
import asyncio
from typing import Any, Dict, Optional, Callable
from functools import wraps
import threading


def generate_stable_id(title: str, link: str, guid: Optional[str] = None) -> str:
    """Generate a stable, unique identifier for a press item.
    
    Uses GUID if available, otherwise creates a hash from title and link.
    
    Args:
        title: Press item title
        link: Press item link URL
        guid: Optional GUID from RSS feed
        
    Returns:
        Stable unique identifier
    """
    if guid:
        # Use GUID directly if available
        guid_clean = guid.strip()
        if guid_clean:
            return guid_clean
    
    # Generate hash from title and link
    combined = f"{title.strip()}|{link.strip()}"
    return hashlib.sha1(combined.encode('utf-8')).hexdigest()


class TTLCache:
    """Simple TTL (Time-To-Live) cache implementation."""
    
    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        """Initialize TTL cache.
        
        Args:
            ttl_seconds: Time-to-live in seconds
            max_size: Maximum number of items to cache
        """
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if expired/missing
        """
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                else:
                    # Expired, remove it
                    del self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            # Remove oldest items if at capacity
            if len(self._cache) >= self.max_size:
                # Remove expired items first
                current_time = time.time()
                expired_keys = [
                    k for k, (_, ts) in self._cache.items()
                    if current_time - ts >= self.ttl
                ]
                for k in expired_keys:
                    del self._cache[k]
                
                # Still at capacity? Remove oldest
                if len(self._cache) >= self.max_size:
                    oldest_key = min(
                        self._cache.keys(),
                        key=lambda k: self._cache[k][1]
                    )
                    del self._cache[oldest_key]
            
            self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Clear all cached items."""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)


def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """Decorator for retrying function calls with exponential backoff.
    
    Supports both sync and async functions.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Multiplication factor for exponential backoff
        exceptions: Tuple of exception types to retry on
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff_factor ** attempt)
                        await asyncio.sleep(wait_time)
                    else:
                        raise
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff_factor ** attempt)
                        time.sleep(wait_time)
                    else:
                        raise
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
        
        # Return async wrapper for async functions, sync wrapper for sync functions
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator


def sanitize_string(text: str) -> str:
    """Sanitize string by trimming whitespace and removing control characters.
    
    Args:
        text: Input string
        
    Returns:
        Sanitized string
    """
    if not text:
        return ""
    
    # Remove control characters except whitespace
    import re
    cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    # Trim and normalize whitespace
    return ' '.join(cleaned.split())