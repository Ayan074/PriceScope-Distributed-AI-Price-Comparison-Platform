"""
MCP (Model Context Protocol) Server.

Exposes product search, normalization, and ranking as MCP tools
that can be called by LLMs through the standard MCP protocol.

Tools:
    1. search_amazon    — Search Amazon via microservice
    2. search_ebay      — Search eBay via microservice
    3. search_google    — Search Google Shopping via microservice
    4. search_walmart   — Search Walmart via microservice
    5. normalize_data   — Normalize product data (prices to INR, clean titles)
    6. rank_products    — Rank by price, rating, and value score
"""

import sys
import os
os.environ["PORT"] = "8010"
os.environ["HOST"] = "0.0.0.0"
import json
import logging
from mcp.server.fastmcp import FastMCP

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp.server.fastmcp import FastMCP
import httpx

from shared.utils import (
    normalize_price,
    normalize_title,
    convert_to_inr,
    calculate_value_score,
    deduplicate_products,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MCP] %(message)s")
logger = logging.getLogger(__name__)

# Service URLs
AMAZON_URL = os.getenv("AMAZON_SERVICE_URL", "http://localhost:8005")
EBAY_URL = os.getenv("EBAY_SERVICE_URL", "http://localhost:8003")
GOOGLE_URL = os.getenv("GOOGLE_SERVICE_URL", "http://localhost:8004")
WALMART_URL = os.getenv("WALMART_SERVICE_URL", "http://localhost:8006")

# Initialize MCP server
mcp = FastMCP("ProductComparisonTools")


# ─── Search Tools (one per source) ───────────────────────────────────────────

async def _search_service(service_name: str, service_url: str, product_name: str) -> str:
    """Generic helper to search a microservice."""
    logger.info(f"MCP Tool: search_{service_name.lower()}({product_name})")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{service_url}/search",
                params={"query": product_name}
            )
            response.raise_for_status()
            data = response.json()
            return json.dumps(data.get("products", []), indent=2)
    except httpx.ConnectError:
        logger.error(f"{service_name} service is not running")
        return json.dumps({"error": f"{service_name} service unavailable", "products": []})
    except Exception as e:
        logger.error(f"{service_name} search error: {e}")
        return json.dumps({"error": str(e), "products": []})


@mcp.tool()
async def search_amazon(product_name: str) -> str:
    """
    Search for products on Amazon (India, prices in INR, uses Selenium scraping).

    Args:
        product_name: The product to search for

    Returns:
        JSON string containing a list of products with title, price, rating, reviews, url
    """
    return await _search_service("Amazon", AMAZON_URL, product_name)


@mcp.tool()
async def search_ebay(product_name: str) -> str:
    """
    Search for products on eBay (international, prices in USD, lightweight scraping).

    Args:
        product_name: The product to search for

    Returns:
        JSON string containing a list of products with title, price, rating, reviews, url
    """
    return await _search_service("eBay", EBAY_URL, product_name)


@mcp.tool()
async def search_google(product_name: str) -> str:
    """
    Search for products on Google Shopping (aggregated seller prices in INR, via SerpAPI).

    Args:
        product_name: The product to search for

    Returns:
        JSON string containing a list of products with title, price, rating, reviews, url
    """
    return await _search_service("Google", GOOGLE_URL, product_name)


@mcp.tool()
async def search_walmart(product_name: str) -> str:
    """
    Search for products on Walmart (US, prices in USD, scraping fallback).

    Args:
        product_name: The product to search for

    Returns:
        JSON string containing a list of products with title, price, rating, reviews, url
    """
    return await _search_service("Walmart", WALMART_URL, product_name)


# ─── Normalization + Ranking Tools ───────────────────────────────────────────

@mcp.tool()
def normalize_data(products_json: str) -> str:
    """
    Normalize product data: convert prices to INR, clean titles, remove duplicates.

    Args:
        products_json: JSON string containing a list of product objects

    Returns:
        JSON string with normalized product data
    """
    logger.info("MCP Tool: normalize_data")
    try:
        products = json.loads(products_json)

        if isinstance(products, dict):
            if "error" in products:
                return json.dumps([])
            products = products.get("products", [])

        normalized = []
        for product in products:
            product["title"] = normalize_title(product.get("title", ""))

            price = product.get("price", 0)
            currency = product.get("currency", "INR")

            if isinstance(price, str):
                price = normalize_price(price) or 0

            product["price"] = float(price)
            product["normalized_price_inr"] = convert_to_inr(float(price), currency)

            rating = float(product.get("rating", 0))
            reviews = int(product.get("reviews", 0))
            product["value_score"] = calculate_value_score(
                product["normalized_price_inr"], rating, reviews
            )

            normalized.append(product)

        deduplicated = deduplicate_products(normalized)
        return json.dumps(deduplicated, indent=2)

    except Exception as e:
        logger.error(f"Normalization error: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def rank_products(products_json: str) -> str:
    """
    Rank products and identify best price, best rating, and best value for money.

    Args:
        products_json: JSON string containing normalized product data

    Returns:
        JSON string with ranked results including best_price, best_rating, best_value
    """
    logger.info("MCP Tool: rank_products")
    try:
        products = json.loads(products_json)

        if not products or isinstance(products, dict):
            return json.dumps({
                "products": [],
                "best_price": None,
                "best_rating": None,
                "best_value": None,
            })

        by_price = sorted(products, key=lambda p: p.get("normalized_price_inr", float("inf")))
        by_rating = sorted(
            products,
            key=lambda p: (p.get("rating", 0), p.get("reviews", 0)),
            reverse=True,
        )
        by_value = sorted(
            products,
            key=lambda p: p.get("value_score", 0),
            reverse=True,
        )

        result = {
            "products": products,
            "best_price": by_price[0] if by_price else None,
            "best_rating": by_rating[0] if by_rating else None,
            "best_value": by_value[0] if by_value else None,
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Ranking error: {e}")
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    import os
    import uvicorn
    
    target_port = int(os.environ.get("PORT", 8010))
    
    # FastMCP stubbornly defaults to port 8000. 
    # We intercept Uvicorn's run method here to forcefully redirect it to 8010.
    original_run = uvicorn.run
    
    def patched_run(*args, **kwargs):
        kwargs["host"] = "0.0.0.0"
        kwargs["port"] = target_port
        original_run(*args, **kwargs)
        
    uvicorn.run = patched_run
    
    # Now when FastMCP tries to start, it will be trapped and forced onto 8010
    mcp.run(transport="sse")