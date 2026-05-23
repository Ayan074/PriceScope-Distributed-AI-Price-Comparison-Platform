"""
eBay Microservice - FastAPI application.
Handles product search requests for eBay platform.
Runs on port 8003.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging

from services.ebay.scraper import search_ebay

logging.basicConfig(level=logging.INFO, format="%(asctime)s [EBAY] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="eBay Product Service",
    description="Microservice for fetching eBay product data",
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
    return {"service": "eBay Product Service", "status": "running", "port": 8003}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ebay"}


@app.get("/search")
async def search(query: str = Query(..., min_length=1)):
    """Search for products on eBay."""
    try:
        logger.info(f"Searching eBay for: {query}")
        products = await search_ebay(query)
        logger.info(f"Found {len(products)} products on eBay for '{query}'")
        return {"products": products, "source": "eBay", "query": query}
    except Exception as e:
        logger.error(f"Error searching eBay: {e}")
        raise HTTPException(status_code=500, detail=f"eBay search failed: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
