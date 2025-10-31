"""RSS client for fetching and parsing Köln press releases."""

import os
from typing import List, Optional
from xml.etree import ElementTree as ET
import httpx
from lxml import etree

from .models import PressItem, from_rss_item
from .utils import TTLCache, retry_on_failure


# RSS feed URL
RSS_URL = "https://www.stadt-koeln.de/externe-dienste/rss/pressemeldungen.xml"


class RssClient:
    """Client for fetching and parsing RSS feed from Stadt Köln."""
    
    def __init__(
        self,
        cache_ttl: Optional[int] = None,
        http_timeout: Optional[int] = None,
        max_retries: Optional[int] = None
    ):
        """Initialize RSS client.
        
        Args:
            cache_ttl: Cache TTL in seconds (default from env or 300)
            http_timeout: HTTP timeout in seconds (default from env or 8)
            max_retries: Maximum retry attempts (default from env or 3)
        """
        self.rss_url = RSS_URL
        self.cache_ttl = cache_ttl or int(os.getenv('CACHE_TTL', '300'))
        self.http_timeout = http_timeout or int(os.getenv('HTTP_TIMEOUT', '8'))
        self.max_retries = max_retries or int(os.getenv('HTTP_RETRIES', '3'))
        
        # Initialize cache
        self._cache = TTLCache(ttl_seconds=self.cache_ttl)
        self._cached_items: Optional[List[PressItem]] = None
        self._last_fetch: Optional[float] = None
    
    @retry_on_failure(
        max_attempts=3,
        delay=1.0,
        backoff_factor=2.0,
        exceptions=(httpx.RequestError, httpx.HTTPStatusError)
    )
    async def fetch_raw(self) -> bytes:
        """Fetch raw RSS feed data.
        
        Returns:
            Raw RSS XML data as bytes
            
        Raises:
            httpx.RequestError: If HTTP request fails
            httpx.HTTPStatusError: If HTTP response indicates error
        """
        headers = {
            'User-Agent': 'fastmcp-koeln-presse/1.0',
            'Accept': 'application/rss+xml, application/xml, text/xml'
        }
        
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            response = await client.get(
                self.rss_url,
                headers=headers
            )
            response.raise_for_status()
            return response.content
    
    def parse_items(self, xml_data: bytes) -> List[PressItem]:
        """Parse RSS XML data into PressItem objects.
        
        Args:
            xml_data: Raw RSS XML data
            
        Returns:
            List of PressItem objects
            
        Raises:
            ET.ParseError: If XML parsing fails
            ValueError: If required XML structure is missing
        """
        try:
            # Parse XML with lxml for better error handling
            root = etree.fromstring(xml_data)
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Invalid RSS XML: {e}") from e
        
        # Find channel element
        channel = root.find('channel')
        if channel is None:
            raise ValueError("RSS feed missing 'channel' element")
        
        # Find all item elements
        items = []
        for item_elem in channel.findall('item'):
            try:
                press_item = from_rss_item(item_elem)
                items.append(press_item)
            except Exception as e:
                # Log error but continue parsing other items
                print(f"Error parsing RSS item: {e}")
                continue
        
        if not items:
            raise ValueError("No valid press items found in RSS feed")
        
        return items
    
    async def load_items_cached(self) -> List[PressItem]:
        """Load press items with caching.
        
        Returns:
            List of PressItem objects
            
        Raises:
            Exception: If fetching and parsing fails
        """
        import time
        
        current_time = time.time()
        
        # Check if we have valid cached data
        if (
            self._cached_items is not None 
            and self._last_fetch is not None
            and current_time - self._last_fetch < self.cache_ttl
        ):
            return self._cached_items
        
        try:
            # Fetch fresh data
            xml_data = await self.fetch_raw()
            items = self.parse_items(xml_data)
            
            # Update cache
            self._cached_items = items
            self._last_fetch = current_time
            
            return items
            
        except Exception as e:
            # Return stale cache if available, otherwise re-raise
            if self._cached_items is not None:
                return self._cached_items
            raise
    
    async def get_item_by_id(self, item_id: str) -> Optional[PressItem]:
        """Get a specific press item by ID.
        
        Args:
            item_id: Unique identifier for the press item
            
        Returns:
            PressItem if found, None otherwise
        """
        items = await self.load_items_cached()
        for item in items:
            if item.id == item_id:
                return item
        return None
    
    async def search_items(
        self, 
        query: str, 
        limit: int = 20
    ) -> List[PressItem]:
        """Search press items by query.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of matching PressItem objects, sorted by relevance
        """
        items = await self.load_items_cached()
        query_lower = query.lower().strip()
        
        if not query_lower:
            return items[:limit]
        
        # Score items based on query match
        scored_items = []
        for item in items:
            score = self._score_item(item, query_lower)
            if score > 0:
                scored_items.append((score, item))
        
        # Sort by score (descending) and return top results
        scored_items.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_items[:limit]]
    
    def _score_item(self, item: PressItem, query: str) -> int:
        """Score an item based on query match.
        
        Args:
            item: Press item to score
            query: Search query (lowercase)
            
        Returns:
            Relevance score (higher = more relevant)
        """
        score = 0
        
        # Title matches are most relevant
        if query in (item.title or "").lower():
            score += 3
        
        # Category matches are moderately relevant
        for category in item.categories:
            if query in category.lower():
                score += 2
        
        # Description matches are least relevant
        if query in (item.description or "").lower():
            score += 1
        
        return score
    
    def get_categories(self) -> List[str]:
        """Get all unique categories from cached items.
        
        Returns:
            Sorted list of unique categories
        """
        if self._cached_items is None:
            return []
        
        categories = set()
        for item in self._cached_items:
            categories.update(item.categories)
        
        return sorted(list(categories))
    
    async def refresh_cache(self) -> None:
        """Force refresh of cached data."""
        import time
        
        try:
            xml_data = await self.fetch_raw()
            items = self.parse_items(xml_data)
            
            self._cached_items = items
            self._last_fetch = time.time()
            
        except Exception as e:
            raise Exception(f"Failed to refresh cache: {e}") from e
    
    def clear_cache(self) -> None:
        """Clear the cache."""
        self._cached_items = None
        self._last_fetch = None
        self._cache.clear()