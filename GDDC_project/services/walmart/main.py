"""
Walmart Product Microservice — FastAPI application.

Handles product search requests for Walmart platform.
Runs on port 8006.

This is a worker node in the distributed architecture.
Uses SerpAPI walmart engine as primary, with direct scraping as fallback.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging

from services.walmart.scraper import search_walmart

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [WALMART] %(message)s")
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Walmart Product Service",
    description="Microservice for fetching Walmart product data (scraping fallback)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"service": "Walmart Product Service", "status": "running", "port": 8006, "method": "scraping"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "walmart"}


@app.get("/search")
async def search(query: str = Query(..., min_length=1)):
    """Search for products on Walmart."""
    try:
        logger.info(f"🔍 Searching Walmart for: {query}")
        products = await search_walmart(query)
        logger.info(f"✅ Found {len(products)} products on Walmart for '{query}'")
        return {"products": products, "source": "Walmart", "query": query}
    except Exception as e:
        logger.error(f"❌ Error searching Walmart: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Walmart search failed: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
