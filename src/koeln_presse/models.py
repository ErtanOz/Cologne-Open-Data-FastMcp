"""Data models for Köln Presse RSS items."""

from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, AnyUrl
from .utils import generate_stable_id


class PressItem(BaseModel):
    """Represents a single press release item from RSS feed."""
    
    id: str = Field(..., description="Unique identifier for the press item")
    title: str = Field(..., description="Title of the press release")
    link: AnyUrl = Field(..., description="URL to the full press release")
    description: Optional[str] = Field(None, description="Description or content summary")
    published_at: datetime = Field(..., description="Publication timestamp")
    categories: List[str] = Field(default_factory=list, description="List of categories")
    raw_guid: Optional[str] = Field(None, description="Raw GUID from RSS feed")
    source: Literal["rss:stadt-koeln"] = Field(
        default="rss:stadt-koeln", 
        description="RSS source identifier"
    )
    
    class Config:
        """Pydantic model configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "id": "abc123",
                "title": "Stadt Köln informiert über...",
                "link": "https://www.stadt-koeln.de/pressemeldungen/123",
                "description": "<p>Köln, den 15. Oktober 2024</p>",
                "published_at": "2024-10-15T10:30:00+02:00",
                "categories": ["Politik", "Verkehr"],
                "source": "rss:stadt-koeln"
            }
        }


def from_rss_item(
    item_element,
    base_url: str = "https://www.stadt-koeln.de"
) -> PressItem:
    """Create a PressItem from an RSS XML element.
    
    Args:
        item_element: lxml element representing an RSS item
        base_url: Base URL for resolving relative links
        
    Returns:
        PressItem instance parsed from RSS data
    """
    import html
    
    # Extract title
    title_elem = item_element.find("title")
    title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Unbekannter Titel"
    
    # Extract link
    link_elem = item_element.find("link")
    link_text = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
    if link_text.startswith("/"):
        link_text = base_url + link_text
    elif not link_text.startswith("http"):
        link_text = base_url + "/" + link_text.lstrip("/")
    
    # Extract description - try content:encoded first, then description
    description = None
    content_elem = item_element.find("{http://purl.org/rss/1.0/modules/content/}encoded")
    if content_elem is not None and content_elem.text:
        description = content_elem.text
    else:
        desc_elem = item_element.find("description")
        if desc_elem is not None and desc_elem.text:
            description = desc_elem.text
    
    # Extract publication date
    pubdate_elem = item_element.find("pubDate")
    published_at = datetime.now()
    if pubdate_elem is not None and pubdate_elem.text:
        from dateutil import parser
        try:
            published_at = parser.parse(pubdate_elem.text.strip())
        except Exception:
            pass
    
    # Extract categories
    categories = []
    for cat_elem in item_element.findall("category"):
        if cat_elem.text and cat_elem.text.strip():
            cat_text = cat_elem.text.strip()
            if cat_text:
                categories.append(cat_text)
    
    # Extract GUID
    guid_elem = item_element.find("guid")
    raw_guid = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
    
    # Generate stable ID
    item_id = generate_stable_id(title, link_text, raw_guid)
    
    return PressItem(
        id=item_id,
        title=title,
        link=link_text,
        description=description,
        published_at=published_at,
        categories=categories,
        raw_guid=raw_guid,
        source="rss:stadt-koeln"
    )