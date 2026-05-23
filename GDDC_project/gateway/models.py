from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class CompareRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)

class CompareResponse(BaseModel):
    query: str
    timestamp: str
    products: List[Dict[str, Any]] = []
    best_price: Optional[Dict[str, Any]] = None
    best_rating: Optional[Dict[str, Any]] = None
    best_value: Optional[Dict[str, Any]] = None
    insights: str = ""
    total_results: int = 0
    sources_searched: List[str] = []
    cached: bool = False
    llm_used: bool = False
    processing_mode: str = "async"
    processing_time_ms: float = 0.0