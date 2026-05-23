import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from services.target.scraper import scrape_target

app = FastAPI(title="Target Scraper Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/search")
async def search_target_api(query: str = Query(..., min_length=1)):
    products = await scrape_target(query)
    return {"source": "Target", "query": query, "products": products}

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Target"}