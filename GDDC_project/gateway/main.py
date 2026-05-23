"""
API Gateway - Main FastAPI application.

This is the central entry point that:
- Serves the frontend static files
- Exposes REST API endpoints for product comparison
- Orchestrates calls to microservices
- Manages search history
"""

import sys
import os
import logging
from contextlib import asynccontextmanager

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from gateway.config import settings
from gateway.models import CompareRequest, CompareResponse
from gateway.orchestrator import compare_products, get_all_health
from shared.cache import get_search_history

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GATEWAY] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# --- Lifespan Manager (Replaces on_event) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup logic
    logger.info("🚀 Gateway starting up...")
    logger.info(f"   LLM: {'OpenAI (' + settings.LLM_MODEL + ')' if settings.has_openai_key else 'Rule-based fallback'}")
    logger.info(f"   Services: {list(settings.service_urls.keys())}")
    logger.info(f"   Sources: Amazon (Selenium), eBay (Scraping), Google (SerpAPI), Walmart (Scraping)")
    
    yield # This yields control to FastAPI to run the app
    
    # 2. Shutdown logic
    from gateway.orchestrator import _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
    logger.info("Gateway shutting down...")


# Create FastAPI app (Initialized ONLY ONCE with lifespan)
app = FastAPI(
    title="Product Price Comparison Platform",
    description="Distributed product comparison using LLM + MCP architecture",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Routes ---

@app.post("/api/compare", response_model=None)
async def compare(request: CompareRequest):
    """
    Compare product prices across multiple platforms.

    Triggers parallel fetching from Amazon, Flipkart, and eBay,
    normalizes data, runs LLM analysis, and returns ranked results.
    """
    try:
        logger.info(f"🔍 Compare request: '{request.query}'")
        result = await compare_products(request.query)
        return result
    except Exception as e:
        logger.error(f"❌ Compare failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@app.get("/api/health")
async def health():
    """Health check for all services."""
    return await get_all_health()

@app.get("/health")
def simple_health():
    return {"status": "ok"}


@app.get("/api/history")
async def history():
    """Get recent search history."""
    try:
        searches = get_search_history(limit=20)
        return {"history": searches}
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        return {"history": []}


@app.get("/api/config")
async def config():
    """Get public configuration info."""
    return {
        "llm_available": settings.has_openai_key,
        "llm_model": settings.LLM_MODEL if settings.has_openai_key else "rule-based",
        "services": list(settings.service_urls.keys()),
    }


# --- Static Files (Frontend) ---

# Serve frontend files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page."""
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Product Price Comparison API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.GATEWAY_PORT)