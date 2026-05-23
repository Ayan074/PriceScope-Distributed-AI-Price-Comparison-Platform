"""
Amazon Product Microservice — FastAPI application.

Handles product search requests for Amazon platform using Selenium scraper.
Runs on port 8005.

This is a worker node in the distributed architecture.
The gateway dispatches requests here via Celery tasks or direct HTTP calls.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging

from services.amazon.scraper import search_amazon

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [AMAZON] %(message)s")
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Amazon Product Service",
    description="Microservice for fetching Amazon product data via Selenium",
    version="2.0.0"
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
    return {"service": "Amazon Product Service", "status": "running", "port": 8005, "method": "Selenium"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "amazon"}


@app.get("/search")
async def search(query: str = Query(..., min_length=1)):
    """Search for products on Amazon using Selenium scraping."""
    try:
        logger.info(f"🔍 Searching Amazon for: {query}")
        products = await search_amazon(query)
        logger.info(f"✅ Found {len(products)} products on Amazon for '{query}'")
        return {"products": products, "source": "Amazon", "query": query}
    except Exception as e:
        logger.error(f"❌ Error searching Amazon: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Amazon search failed: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)