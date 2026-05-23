"""
Google Shopping Microservice - FastAPI application.
Handles product search requests for Google Shopping platform.
Runs on port 8004.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging

from services.google.scraper import search_google

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GOOGLE] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Google Shopping Product Service",
    description="Microservice for fetching Google Shopping product data",
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
    return {"service": "Google Shopping Product Service", "status": "running", "port": 8004}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "google"}


@app.get("/search")
async def search(query: str = Query(..., min_length=1)):
    """Search for products on Google Shopping."""
    try:
        logger.info(f"Searching Google Shopping for: {query}")
        products = await search_google(query)
        logger.info(f"Found {len(products)} products on Google Shopping for '{query}'")
        return {"products": products, "source": "Google", "query": query}
    except Exception as e:
        logger.error(f"Error searching Google Shopping: {e}")
        raise HTTPException(status_code=500, detail=f"Google Shopping search failed: {str(e)}")


@app.get("/health")
def health():
    return {"status": "ok"}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
