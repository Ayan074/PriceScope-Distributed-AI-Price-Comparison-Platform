"""
Google Shopping Real Product Scraper.

Uses SerpApi's google_shopping engine for reliable product data extraction.
"""

import os
import logging
import re
from dotenv import load_dotenv

import httpx

# Ensure we load from project root .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

async def search_google(query: str, max_results: int = 8) -> list[dict]:
    """Search product data using SerpApi Google Shopping engine."""
    if not SERPAPI_KEY:
        logger.error("SERPAPI_KEY is not set in environment variables.")
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_shopping",
        "q": query,
        "hl": "en",
        "gl": "in",
        "api_key": SERPAPI_KEY,
        "num": max_results,
    }

    logger.info(f"Scraping SerpApi Google Shopping for query: '{query}'")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()

        data = resp.json()
        shopping_results = data.get("shopping_results", [])
        
        products = []
        for item in shopping_results[:max_results]:
            title = item.get("title", "")
            
            price_val = 0.0
            currency = "INR"
            
            if "extracted_price" in item:
                price_val = float(item["extracted_price"])
            elif "price" in item:
                p_str = item["price"].replace(",", "")
                m = re.search(r'[\d.]+', p_str)
                if m:
                    price_val = float(m.group(0))
                if "$" in item["price"]:
                    currency = "USD"
            
            if price_val <= 0:
                continue
                
            products.append({
                "title": title[:200],
                "price": price_val,
                "currency": currency,
                "rating": float(item.get("rating", 0.0)),
                "reviews": int(item.get("reviews", 0)),
                "url": item.get("link", item.get("product_link", "")),
                "source": "Google",
                "image_url": item.get("thumbnail", ""),
                "seller": item.get("source", ""),
            })

        logger.info(f"SerpApi Google Shopping: returned {len(products)} products for '{query}'")
        return products

    except Exception as e:
        logger.error(f"SerpApi Google Shopping failed: {e}")
        return []
