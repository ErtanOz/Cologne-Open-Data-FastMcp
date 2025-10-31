"""Tests for RSS client functionality."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from lxml import etree

from koeln_presse.rss_client import RssClient
from koeln_presse.models import PressItem


# Sample RSS XML for testing
SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>Pressemitteilungen Stadt Köln</title>
    <link>https://www.stadt-koeln.de</link>
    <description>RSS Feed der Pressemitteilungen</description>
    
    <item>
        <title>Stadt Köln informiert über Baustellen</title>
        <link>/pressemeldungen/123</link>
        <description><![CDATA[<p>Köln, den 15. Oktober 2024</p><p>Neue Baustellen in der Innenstadt</p>]]></description>
        <pubDate>Mon, 15 Oct 2024 10:30:00 +0200</pubDate>
        <category>Verkehr</category>
        <category>Baustellen</category>
        <guid isPermaLink="false">item-123</guid>
    </item>
    
    <item>
        <title>Neue Kulturveranstaltungen im November</title>
        <link>/pressemeldungen/124</link>
        <description>Köln präsentiert neue Kulturtermine für den November</description>
        <pubDate>Mon, 14 Oct 2024 14:15:00 +0200</pubDate>
        <category>Kultur</category>
        <guid isPermaLink="false">item-124</guid>
    </item>
    
    <item>
        <title>Kölner Zoo öffnet neue Anlage</title>
        <link>https://www.stadt-koeln.de/pressemeldungen/125</link>
        <content:encoded><![CDATA[<p>Moderne Anlage für afrikanische Tiere</p>]]></content:encoded>
        <pubDate>Sun, 13 Oct 2024 09:00:00 +0200</pubDate>
        <category>Tierpark</category>
        <guid isPermaLink="false">item-125</guid>
    </item>
</channel>
</rss>"""


class TestRssClient:
    """Test suite for RssClient."""
    
    @pytest.fixture
    def client(self):
        """Create a test client instance."""
        return RssClient(cache_ttl=60, http_timeout=5, max_retries=2)
    
    @pytest.fixture
    def sample_xml_bytes(self):
        """Sample RSS XML as bytes."""
        return SAMPLE_RSS_XML.encode('utf-8')
    
    def test_client_initialization(self):
        """Test client initialization with custom settings."""
        client = RssClient(cache_ttl=120, http_timeout=10, max_retries=5)
        
        assert client.cache_ttl == 120
        assert client.http_timeout == 10
        assert client.max_retries == 5
        assert client.rss_url == "https://www.stadt-koeln.de/externe-dienste/rss/pressemeldungen.xml"
    
    @pytest.mark.asyncio
    async def test_parse_items(self, client, sample_xml_bytes):
        """Test parsing RSS XML into PressItem objects."""
        items = client.parse_items(sample_xml_bytes)
        
        assert len(items) == 3
        
        # Check first item
        item1 = items[0]
        assert item1.title == "Stadt Köln informiert über Baustellen"
        assert item1.link == "https://www.stadt-koeln.de/pressemeldungen/123"
        assert item1.categories == ["Verkehr", "Baustellen"]
        assert item1.raw_guid == "item-123"
        assert item1.source == "rss:stadt-koeln"
        
        # Check second item
        item2 = items[1]
        assert item2.title == "Neue Kulturveranstaltungen im November"
        assert item2.link == "https://www.stadt-koeln.de/pressemeldungen/124"
        assert item2.categories == ["Kultur"]
        assert item2.source == "rss:stadt-koeln"
        
        # Check third item (with content:encoded)
        item3 = items[2]
        assert item3.title == "Kölner Zoo öffnet neue Anlage"
        assert "Moderne Anlage für afrikanische Tiere" in item3.description
    
    @pytest.mark.asyncio
    async def test_parse_items_invalid_xml(self, client):
        """Test parsing invalid XML raises appropriate error."""
        invalid_xml = b"<invalid>xml</wrong>"
        
        with pytest.raises(ValueError, match="Invalid RSS XML"):
            client.parse_items(invalid_xml)
    
    @pytest.mark.asyncio
    async def test_parse_items_missing_channel(self, client):
        """Test parsing XML missing channel element."""
        invalid_xml = b"<rss><item></item></rss>"
        
        with pytest.raises(ValueError, match="RSS feed missing 'channel' element"):
            client.parse_items(invalid_xml)
    
    @pytest.mark.asyncio
    async def test_parse_items_no_items(self, client):
        """Test parsing XML with no items."""
        xml_no_items = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>Test</title></channel></rss>"""
        
        with pytest.raises(ValueError, match="No valid press items found"):
            client.parse_items(xml_no_items)
    
    @pytest.mark.asyncio
    async def test_load_items_cached(self, client, sample_xml_bytes):
        """Test loading items with caching."""
        # Mock the fetch_raw method
        with patch.object(client, 'fetch_raw', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_xml_bytes
            
            # First call should fetch from network
            items1 = await client.load_items_cached()
            assert mock_fetch.called
            assert len(items1) == 3
            
            # Reset mock
            mock_fetch.reset_mock()
            
            # Second call should use cache
            items2 = await client.load_items_cached()
            assert not mock_fetch.called  # Should not fetch again
            assert items1 == items2
    
    @pytest.mark.asyncio
    async def test_get_item_by_id(self, client, sample_xml_bytes):
        """Test getting specific item by ID."""
        with patch.object(client, 'fetch_raw', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_xml_bytes
            
            # Load items first
            await client.load_items_cached()
            
            # Get existing item
            item = await client.get_item_by_id("item-123")
            assert item is not None
            assert item.title == "Stadt Köln informiert über Baustellen"
            
            # Get non-existing item
            item = await client.get_item_by_id("nonexistent")
            assert item is None
    
    @pytest.mark.asyncio
    async def test_search_items(self, client, sample_xml_bytes):
        """Test searching items by query."""
        with patch.object(client, 'fetch_raw', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_xml_bytes
            
            # Load items first
            await client.load_items_cached()
            
            # Search by title
            results = await client.search_items("Baustellen", limit=10)
            assert len(results) >= 1
            assert any("Baustellen" in item.title for item in results)
            
            # Search by category
            results = await client.search_items("Kultur", limit=10)
            assert len(results) >= 1
            assert any("Kultur" in item.categories for item in results)
            
            # Search with limit
            results = await client.search_items("Stadt", limit=1)
            assert len(results) == 1
            
            # Search with no matches
            results = await client.search_items("xyz123", limit=10)
            assert len(results) == 0
    
    def test_get_categories(self, client, sample_xml_bytes):
        """Test getting all categories."""
        # Manually set cached items
        items = client.parse_items(sample_xml_bytes)
        client._cached_items = items
        
        categories = client.get_categories()
        
        expected_categories = {"Verkehr", "Baustellen", "Kultur", "Tierpark"}
        assert set(categories) == expected_categories
        assert categories == sorted(categories)  # Should be sorted
    
    @pytest.mark.asyncio
    async def test_refresh_cache(self, client, sample_xml_bytes):
        """Test manually refreshing cache."""
        with patch.object(client, 'fetch_raw', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_xml_bytes
            
            # Set initial cache state
            client._cached_items = []
            client._last_fetch = 0
            
            # Refresh cache
            await client.refresh_cache()
            
            # Verify cache was updated
            assert len(client._cached_items) == 3
            assert client._last_fetch > 0
            
            # Verify fetch was called
            mock_fetch.assert_called_once()
    
    def test_clear_cache(self, client):
        """Test clearing cache."""
        # Set cache state
        client._cached_items = [Mock(spec=PressItem)]
        client._last_fetch = 1234567890
        client._cache.set("test", "value")
        
        # Clear cache
        client.clear_cache()
        
        # Verify cache is cleared
        assert client._cached_items is None
        assert client._last_fetch is None
        assert client._cache.size() == 0
    
    @pytest.mark.asyncio
    async def test_score_item(self, client):
        """Test item scoring for search."""
        # Create sample item
        item = PressItem(
            id="test-1",
            title="Kölner Stadtpark wird renoviert",
            link="https://example.com",
            description="Renovierung des Stadtparks in Köln",
            published_at=datetime.now(),
            categories=["Park", "Renovierung"],
            source="rss:stadt-koeln"
        )
        
        # Test title match (highest score)
        score = client._score_item(item, "stadtpark")
        assert score == 3  # Title match
        
        # Test category match (medium score)
        score = client._score_item(item, "park")
        assert score == 2  # Category match
        
        # Test description match (lowest score)
        score = client._score_item(item, "renovierung")
        assert score == 1  # Description match
        
        # Test no match
        score = client._score_item(item, "xyz")
        assert score == 0  # No match
    
    @pytest.mark.asyncio
    async def test_stale_cache_fallback(self, client, sample_xml_bytes):
        """Test fallback to stale cache when fetch fails."""
        with patch.object(client, 'fetch_raw', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_xml_bytes
            
            # Load initial data
            items = await client.load_items_cached()
            assert len(items) == 3
            
            # Reset mock and make fetch fail
            mock_fetch.reset_mock()
            mock_fetch.side_effect = Exception("Network error")
            
            # Modify cache to be "stale"
            import time
            client._last_fetch = time.time() - client.cache_ttl - 1
            
            # Should still return stale cache data
            stale_items = await client.load_items_cached()
            assert stale_items == items
            
            # Verify fetch was attempted
            mock_fetch.assert_called_once()