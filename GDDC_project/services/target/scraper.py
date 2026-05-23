import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../..", ".env"))

logger = logging.getLogger(__name__)
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

async def scrape_target(query: str, max_results: int = 8) -> list:
    if not SERPAPI_KEY:
        return []

    logger.info(f"🔍 Searching Target (via Google) for: '{query}'")
    params = {
        "engine": "google_shopping",
        "q": f"{query} target",
        "hl": "en",
        "gl": "in",  # <--- Forces India Region to get accurate INR prices
        "api_key": SERPAPI_KEY
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get("https://serpapi.com/search.json", params=params)
            response.raise_for_status()
            data = response.json()

            raw_products = data.get("shopping_results", [])
            products = []

            for item in raw_products[:max_results]:
                # Clean the price string of $ and ₹ symbols
                price = str(item.get("extracted_price", item.get("price", "0"))).replace("$", "").replace("₹", "").replace(",", "")
                
                product = {
                    "title": item.get("title", ""),
                    "price": price,
                    "currency": "INR",   # <--- Fixed: Tells Gateway not to multiply by 83!
                    # FIX: Look for product_link first, fallback to link
                    "url": item.get("product_link", item.get("link", "")), 
                    "image_url": item.get("thumbnail", ""),
                    "source": "Target",  # <--- Fixed: Uses 'source' instead of 'platform'
                    "rating": item.get("rating", 0),
                    "reviews": item.get("reviews", 0)
                }
                products.append(product)
            return products
    except Exception as e:
        logger.error(f"❌ Target scraping failed: {e}")
        return []