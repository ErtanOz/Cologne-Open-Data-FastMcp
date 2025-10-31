"""Tests for MCP server tools."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from koeln_presse.server import app
from koeln_presse.models import PressItem


class TestMcpTools:
    """Test suite for MCP server tools."""
    
    @pytest.fixture
    def client(self):
        """Create test client for FastAPI app."""
        return TestClient(app)
    
    @pytest.fixture
    def sample_items(self):
        """Create sample press items for testing."""
        return [
            PressItem(
                id="item-1",
                title="Stadt Köln informiert über Baustellen",
                link="https://www.stadt-koeln.de/pressemeldungen/123",
                description="Köln, den 15. Oktober 2024 - Neue Baustellen in der Innenstadt",
                published_at=datetime(2024, 10, 15, 10, 30, 0),
                categories=["Verkehr", "Baustellen"],
                source="rss:stadt-koeln"
            ),
            PressItem(
                id="item-2",
                title="Neue Kulturveranstaltungen im November",
                link="https://www.stadt-koeln.de/pressemeldungen/124",
                description="Köln präsentiert neue Kulturtermine für den November",
                published_at=datetime(2024, 10, 14, 14, 15, 0),
                categories=["Kultur"],
                source="rss:stadt-koeln"
            ),
            PressItem(
                id="item-3",
                title="Kölner Zoo öffnet neue Anlage",
                link="https://www.stadt-koeln.de/pressemeldungen/125",
                description="Moderne Anlage für afrikanische Tiere",
                published_at=datetime(2024, 10, 13, 9, 0, 0),
                categories=["Tierpark"],
                source="rss:stadt-koeln"
            ),
            PressItem(
                id="item-4",
                title="Verkehrseinschränkungen wegen Stadtlauf",
                link="https://www.stadt-koeln.de/pressemeldungen/126",
                description="Am Wochenende wird der Köln Stadtlauf ausgetragen",
                published_at=datetime(2024, 10, 16, 8, 0, 0),
                categories=["Verkehr", "Sport"],
                source="rss:stadt-koeln"
            )
        ]
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        # Mock the RSS client to avoid actual network calls
        with patch('koeln_presse.server.client.load_items_cached') as mock_load:
            mock_load.return_value = []
            
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "fastmcp-koeln-presse"
            assert data["version"] == "1.0.0"
    
    def test_manifest_endpoint(self, client):
        """Test MCP manifest endpoint."""
        response = client.get("/manifest")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "koeln.presse"
        assert data["version"] == "1.0.0"
        assert "tools" in data
        
        # Check all required tools are defined
        tools = data["tools"]
        assert "koeln.presse.latest" in tools
        assert "koeln.presse.search" in tools
        assert "koeln.presse.get" in tools
        assert "koeln.presse.categories" in tools
    
    def test_latest_tool_default(self, client, sample_items):
        """Test latest tool with default parameters."""
        with patch('koeln_presse.server.client.load_items_cached') as mock_load:
            mock_load.return_value = sample_items
            
            response = client.post("/tools/latest", json={})
            
            assert response.status_code == 200
            data = response.json()
            
            assert "items" in data
            items = data["items"]
            assert len(items) == 10  # Should return default 10 or all if less
            
            # Check that items are sorted by date (newest first)
            dates = [item["published_at"] for item in items]
            assert dates == sorted(dates, reverse=True)
    
    def test_latest_tool_with_params(self, client, sample_items):
        """Test latest tool with custom parameters."""
        with patch('koeln_presse.server.client.load_items_cached') as mock_load:
            mock_load.return_value = sample_items
            
            response = client.post("/tools/latest", json={"n": 2})
            
            assert response.status_code == 200
            data = response.json()
            
            items = data["items"]
            assert len(items) == 2
            
            # Verify latest items (sorted by date desc)
            assert items[0]["title"] == "Verkehrseinschränkungen wegen Stadtlauf"  # newest
            assert items[1]["title"] == "Stadt Köln informiert über Baustellen"   # second newest
    
    def test_latest_tool_invalid_params(self, client):
        """Test latest tool with invalid parameters."""
        # Test with n > 100
        response = client.post("/tools/latest", json={"n": 150})
        assert response.status_code == 422  # Validation error
        
        # Test with n < 1
        response = client.post("/tools/latest", json={"n": 0})
        assert response.status_code == 422  # Validation error
    
    def test_search_tool(self, client, sample_items):
        """Test search tool functionality."""
        with patch('koeln_presse.server.client.search_items') as mock_search:
            # Mock search to return specific results
            mock_search.return_value = [
                sample_items[0],  # Has "Baustellen" in title
                sample_items[3]   # Has "Verkehr" in categories
            ]
            
            response = client.post("/tools/search", json={
                "query": "Baustellen",
                "limit": 10
            })
            
            assert response.status_code == 200
            data = response.json()
            
            items = data["items"]
            assert len(items) == 2
            
            # Verify search was called with correct parameters
            mock_search.assert_called_once_with("Baustellen", 10)
    
    def test_search_tool_empty_query(self, client, sample_items):
        """Test search tool with empty query."""
        with patch('koeln_presse.server.client.search_items') as mock_search:
            mock_search.return_value = sample_items[:5]  # Return first 5
            
            response = client.post("/tools/search", json={
                "query": "",
                "limit": 5
            })
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 5
    
    def test_search_tool_no_results(self, client, sample_items):
        """Test search tool with no matching results."""
        with patch('koeln_presse.server.client.search_items') as mock_search:
            mock_search.return_value = []  # No results
            
            response = client.post("/tools/search", json={
                "query": "nonexistent",
                "limit": 10
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []
    
    def test_search_tool_invalid_params(self, client):
        """Test search tool with invalid parameters."""
        # Test with limit > 100
        response = client.post("/tools/search", json={
            "query": "test",
            "limit": 150
        })
        assert response.status_code == 422
        
        # Test with limit < 1
        response = client.post("/tools/search", json={
            "query": "test",
            "limit": 0
        })
        assert response.status_code == 422
    
    def test_get_tool_existing_item(self, client, sample_items):
        """Test get tool with existing item."""
        with patch('koeln_presse.server.client.get_item_by_id') as mock_get:
            mock_get.return_value = sample_items[0]  # Return first item
            
            response = client.post("/tools/get", json={"id": "item-1"})
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["id"] == "item-1"
            assert data["title"] == "Stadt Köln informiert über Baustellen"
            assert data["source"] == "rss:stadt-koeln"
            
            # Verify get was called with correct ID
            mock_get.assert_called_once_with("item-1")
    
    def test_get_tool_nonexistent_item(self, client):
        """Test get tool with non-existent item."""
        with patch('koeln_presse.server.client.get_item_by_id') as mock_get:
            mock_get.return_value = None  # Item not found
            
            response = client.post("/tools/get", json={"id": "nonexistent"})
            
            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"]
    
    def test_get_tool_missing_id(self, client):
        """Test get tool with missing ID parameter."""
        response = client.post("/tools/get", json={})
        assert response.status_code == 422  # Validation error
    
    def test_categories_tool(self, client, sample_items):
        """Test categories tool."""
        with patch('koeln_presse.server.client.load_items_cached') as mock_load:
            mock_load.return_value = sample_items
            
            with patch('koeln_presse.server.client.get_categories') as mock_cats:
                expected_cats = ["Baustellen", "Kultur", "Sport", "Tierpark", "Verkehr"]
                mock_cats.return_value = expected_cats
                
                response = client.post("/tools/categories", json={})
                
                assert response.status_code == 200
                data = response.json()
                
                assert "categories" in data
                categories = data["categories"]
                assert categories == expected_cats
                assert categories == sorted(categories)  # Should be sorted
    
    def test_categories_tool_empty(self, client):
        """Test categories tool when no items loaded."""
        with patch('koeln_presse.server.client.load_items_cached') as mock_load:
            mock_load.return_value = []  # No items
            
            response = client.post("/tools/categories", json={})
            
            assert response.status_code == 200
            data = response.json()
            assert data["categories"] == []
    
    def test_error_handling(self, client):
        """Test error handling in tools."""
        # Mock RSS client to raise exception
        with patch('koeln_presse.server.client.load_items_cached') as mock_load:
            mock_load.side_effect = Exception("Database connection failed")
            
            response = client.post("/tools/latest", json={"n": 5})
            
            assert response.status_code == 500
            data = response.json()
            assert "Failed to fetch latest items" in data["detail"]
    
    def test_data_formatting(self, client, sample_items):
        """Test that data is properly formatted in responses."""
        with patch('koeln_presse.server.client.load_items_cached') as mock_load:
            mock_load.return_value = sample_items
            
            response = client.post("/tools/latest", json={"n": 1})
            
            assert response.status_code == 200
            data = response.json()
            
            item = data["items"][0]
            
            # Check all required fields are present
            required_fields = ["id", "title", "link", "description", "published_at", "categories", "source"]
            for field in required_fields:
                assert field in item
            
            # Check field types
            assert isinstance(item["id"], str)
            assert isinstance(item["title"], str)
            assert isinstance(item["link"], str)
            assert isinstance(item["categories"], list)
            assert isinstance(item["source"], str)
            
            # Check ISO8601 datetime format
            import re
            iso8601_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
            assert re.match(iso8601_pattern, item["published_at"])