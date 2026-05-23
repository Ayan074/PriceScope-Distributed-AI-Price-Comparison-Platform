"""
Shared Pydantic models used across all microservices and the gateway.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Product(BaseModel):
    """Represents a single product from any platform."""
    title: str = Field(..., description="Product title/name")
    price: float = Field(..., description="Price in the platform's currency")
    currency: str = Field(default="INR", description="Currency code (INR, USD, EUR)")
    rating: float = Field(default=0.0, description="Rating out of 5")
    reviews: int = Field(default=0, description="Number of reviews")
    url: str = Field(default="", description="Product page URL")
    source: str = Field(..., description="Platform name (Amazon, Flipkart, eBay)")
    image_url: str = Field(default="", description="Product image URL")
    normalized_price_inr: Optional[float] = Field(default=None, description="Price normalized to INR")
    value_score: Optional[float] = Field(default=None, description="Computed value-for-money score")


class SearchRequest(BaseModel):
    """Incoming search request from the frontend."""
    query: str = Field(..., min_length=1, max_length=200, description="Product search query")


class SearchResponse(BaseModel):
    """Full comparison response returned to the frontend."""
    query: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    products: list[Product] = []
    best_price: Optional[Product] = None
    best_rating: Optional[Product] = None
    best_value: Optional[Product] = None
    insights: str = ""
    total_results: int = 0
    sources_searched: list[str] = []
    cached: bool = False


class ServiceHealth(BaseModel):
    """Health status of a single service."""
    name: str
    status: str  # "healthy" | "unhealthy"
    url: str
    response_time_ms: Optional[float] = None


class HealthResponse(BaseModel):
    """Aggregated health of all services."""
    status: str
    services: list[ServiceHealth] = []
