"""fastMCP Server for Köln Presse RSS feeds."""

import os
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from .rss_client import RssClient
from .models import PressItem
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="fastMCP Köln Presse",
    description="MCP Server für RSS-Pressemitteilungen der Stadt Köln",
    version="1.0.0"
)

# Global RSS client instance
client = RssClient()


# Request/Response Models
class LatestParams(BaseModel):
    """Parameters for the latest press releases tool."""
    n: int = Field(10, ge=1, le=100, description="Number of items to return")


class SearchParams(BaseModel):
    """Parameters for the search press releases tool."""
    query: str = Field(..., description="Search query string")
    limit: int = Field(20, ge=1, le=100, description="Maximum number of results")


class GetParams(BaseModel):
    """Parameters for the get press release tool."""
    id: str = Field(..., description="Press item ID")


class PressItemResponse(BaseModel):
    """Response model for a single press item."""
    id: str
    title: str
    link: str
    description: Optional[str]
    published_at: str
    categories: list[str]
    source: str


class LatestResponse(BaseModel):
    """Response model for latest press releases."""
    items: list[PressItemResponse]


class SearchResponse(BaseModel):
    """Response model for search results."""
    items: list[PressItemResponse]


class CategoriesResponse(BaseModel):
    """Response model for categories list."""
    categories: list[str]


# MCP Tools Implementation
@app.post("/tools/latest", response_model=LatestResponse)
async def latest(params: LatestParams) -> Dict[str, Any]:
    """Get the latest press releases.
    
    Returns a list of the most recent press releases, sorted by publication date.
    
    Args:
        n: Number of items to return (1-100, default: 10)
        
    Returns:
        Dictionary with 'items' key containing list of press items
    """
    try:
        items = await client.load_items_cached()
        
        # Sort by publication date (newest first)
        sorted_items = sorted(
            items, 
            key=lambda x: x.published_at, 
            reverse=True
        )
        
        # Return only requested number
        result_items = sorted_items[:params.n]
        
        # Convert to response format
        response_items = [
            PressItemResponse(
                id=item.id,
                title=item.title,
                link=str(item.link),
                description=item.description,
                published_at=item.published_at.isoformat(),
                categories=item.categories,
                source=item.source
            )
            for item in result_items
        ]
        
        logger.info(f"Returned {len(response_items)} latest items")
        return {"items": [item.dict() for item in response_items]}
        
    except Exception as e:
        logger.error(f"Error in latest tool: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch latest items: {str(e)}"
        )


@app.post("/tools/search", response_model=SearchResponse)
async def search(params: SearchParams) -> Dict[str, Any]:
    """Search press releases by query.
    
    Searches through title, description, and categories for the given query.
    Results are ranked with title matches being most relevant.
    
    Args:
        query: Search query string
        limit: Maximum number of results (1-100, default: 20)
        
    Returns:
        Dictionary with 'items' key containing list of matching press items
    """
    try:
        # Get items and perform search
        results = await client.search_items(params.query, params.limit)
        
        # Convert to response format
        response_items = [
            PressItemResponse(
                id=item.id,
                title=item.title,
                link=str(item.link),
                description=item.description,
                published_at=item.published_at.isoformat(),
                categories=item.categories,
                source=item.source
            )
            for item in results
        ]
        
        logger.info(f"Search for '{params.query}' returned {len(response_items)} items")
        return {"items": [item.dict() for item in response_items]}
        
    except Exception as e:
        logger.error(f"Error in search tool: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Search failed: {str(e)}"
        )


@app.post("/tools/get", response_model=PressItemResponse)
async def get_item(params: GetParams) -> Dict[str, Any]:
    """Get a specific press release by ID.
    
    Retrieves a single press release item by its unique identifier.
    
    Args:
        id: Unique identifier for the press item
        
    Returns:
        Dictionary representing the press item
        
    Raises:
        404: If item with given ID is not found
    """
    try:
        item = await client.get_item_by_id(params.id)
        
        if item is None:
            raise HTTPException(
                status_code=404, 
                detail=f"Press item not found: {params.id}"
            )
        
        # Convert to response format
        response_item = PressItemResponse(
            id=item.id,
            title=item.title,
            link=str(item.link),
            description=item.description,
            published_at=item.published_at.isoformat(),
            categories=item.categories,
            source=item.source
        )
        
        logger.info(f"Retrieved item: {params.id}")
        return response_item.dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get tool: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch item: {str(e)}"
        )


@app.post("/tools/categories", response_model=CategoriesResponse)
async def categories() -> Dict[str, Any]:
    """Get all available categories.
    
    Returns a list of all unique categories from press releases,
    sorted alphabetically.
    
    Returns:
        Dictionary with 'categories' key containing sorted list of categories
    """
    try:
        # Ensure items are loaded
        await client.load_items_cached()
        
        # Get categories
        categories = client.get_categories()
        
        logger.info(f"Returned {len(categories)} categories")
        return {"categories": categories}
        
    except Exception as e:
        logger.error(f"Error in categories tool: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch categories: {str(e)}"
        )


# Health check endpoint
@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint for monitoring and load balancers.
    
    Returns:
        Dictionary with health status information
    """
    try:
        # Try to load items to verify RSS client is working
        await client.load_items_cached()
        return {
            "status": "healthy",
            "service": "fastmcp-koeln-presse",
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503, 
            detail="Service unhealthy"
        )


# MCP Manifest endpoint for fastMCP Cloud compatibility
@app.get("/manifest")
async def get_manifest() -> Dict[str, Any]:
    """Get MCP tool manifest for fastMCP Cloud integration.
    
    Returns:
        Dictionary containing tool definitions and metadata
    """
    return {
        "name": "koeln.presse",
        "version": "1.0.0",
        "description": "Pressemitteilungen Stadt Köln (RSS) als MCP-Tools",
        "tools": {
            "koeln.presse.latest": {
                "description": "Neueste Pressemitteilungen",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "n": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 10,
                            "description": "Anzahl der zurückzugebenden Items"
                        }
                    },
                    "required": []
                }
            },
            "koeln.presse.search": {
                "description": "Pressemitteilungen durchsuchen",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Suchbegriff"
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 20,
                            "description": "Maximale Anzahl Ergebnisse"
                        }
                    },
                    "required": ["query"]
                }
            },
            "koeln.presse.get": {
                "description": "Einzelnes Item per ID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Press Item ID"
                        }
                    },
                    "required": ["id"]
                }
            },
            "koeln.presse.categories": {
                "description": "Alle Kategorien",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    }


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred"
            }
        }
    )


# Main entry point
if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    logger.info(f"Starting fastMCP Köln Presse server on {host}:{port}")
    
    uvicorn.run(
        "koeln_presse.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )