"""
eBay Product Scraper — Dual approach: SerpAPI primary + BS4 fallback.

Strategy:
    1. PRIMARY: SerpAPI 'ebay' engine (reliable, structured JSON)
    2. FALLBACK: Direct HTTP scraping of eBay search pages
    3. If both fail → return [] (fault tolerance)

Prices are in USD, converted to INR by the gateway normalizer.
"""

import os
import re
import logging
from dotenv import load_dotenv

import httpx
from bs4 import BeautifulSoup

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


async def search_ebay(query: str, max_results: int = 8) -> list[dict]:
    """Search eBay: try SerpAPI first, then direct scraping."""
    # Method 1: SerpAPI (most reliable)
    products = await _search_ebay_serpapi(query, max_results)
    if products:
        return products

    # Method 2: Direct scraping (fallback)
    products = await _search_ebay_scrape(query, max_results)
    if products:
        return products

    logger.warning(f"⚠️ eBay: both methods failed for '{query}'")
    return []


async def _search_ebay_serpapi(query: str, max_results: int = 8) -> list[dict]:
    """Search eBay via SerpAPI ebay engine."""
    if not SERPAPI_KEY:
        logger.info("No SERPAPI_KEY set, skipping SerpAPI for eBay")
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "engine": "ebay",
        "_nkw": query,
        "ebay_domain": "ebay.com",
        "LH_BIN": "1",  # Buy It Now only
        "api_key": SERPAPI_KEY,
    }

    logger.info(f"🔍 Trying SerpAPI eBay for: '{query}'")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()

        data = resp.json()
        organic_results = data.get("organic_results", [])

        products = []
        for item in organic_results[:max_results]:
            try:
                title = item.get("title", "")
                if not title:
                    continue

                # Price
                price_val = 0.0
                currency = "USD"

                if "price" in item:
                    price_info = item["price"]
                    if isinstance(price_info, dict):
                        if "extracted" in price_info:
                            price_val = float(price_info["extracted"])
                        elif "raw" in price_info:
                            p_str = price_info["raw"].replace(",", "")
                            m = re.search(r'[\d.]+', p_str)
                            if m:
                                price_val = float(m.group(0))
                            if "₹" in p_str or "INR" in p_str:
                                currency = "INR"
                    elif isinstance(price_info, (int, float)):
                        price_val = float(price_info)

                if price_val <= 0:
                    continue

                # Reviews/Ratings
                rating = 0.0
                reviews = 0
                if "reviews" in item:
                    rating = float(item["reviews"].get("rating", 0.0))
                    reviews = int(item["reviews"].get("amount", 0))

                products.append({
                    "title": title[:200],
                    "price": price_val,
                    "currency": currency,
                    "rating": rating,
                    "reviews": reviews,
                    "url": item.get("link", ""),
                    "source": "eBay",
                    "image_url": item.get("thumbnail", ""),
                })
            except Exception as e:
                logger.debug(f"Skipping eBay SerpAPI item: {e}")
                continue

        logger.info(f"✅ SerpAPI eBay: {len(products)} products for '{query}'")
        return products

    except Exception as e:
        logger.error(f"❌ SerpAPI eBay failed: {e}")
        return []


async def _search_ebay_scrape(query: str, max_results: int = 8) -> list[dict]:
    """
    Direct scraping fallback for eBay.
    Parses search results by finding product links and extracting data.
    """
    search_url = "https://www.ebay.com/sch/i.html"
    params = {
        '_nkw': query,
        '_sacat': '0',
        'LH_BIN': '1',    # Buy It Now
        '_ipg': '60',
    }

    logger.info(f"🔍 Trying direct eBay scraping for: '{query}'")

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(search_url, params=params, headers=HEADERS)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'lxml')

        products = []

        # Strategy: find all /itm/ links and build products from their context
        itm_links = soup.select('a[href*="/itm/"]')

        seen_urls = set()
        for link in itm_links:
            try:
                href = link.get('href', '')

                # Skip duplicates
                item_id = re.search(r'/itm/(\d+)', href)
                if not item_id:
                    continue
                iid = item_id.group(1)
                if iid in seen_urls:
                    continue
                seen_urls.add(iid)

                # Get title from the link text
                title = link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Skip non-product links (navigation, "see all", etc.)
                if any(skip in title.lower() for skip in ['shop on ebay', 'see all', 'sponsored']):
                    continue

                # Navigate up to find the product container
                container = link
                for _ in range(6):
                    if container.parent:
                        container = container.parent
                    else:
                        break

                # Find price in the container
                price_text = ''
                for span in container.find_all(['span', 'div']):
                    text = span.get_text(strip=True)
                    if '$' in text and re.search(r'\$[\d,]+\.?\d*', text):
                        price_text = text
                        break

                if not price_text:
                    continue

                price_match = re.search(r'\$([\d,]+\.?\d*)', price_text)
                if not price_match:
                    continue
                price = float(price_match.group(1).replace(',', ''))
                if price <= 0:
                    continue

                # Image
                img_el = container.find('img')
                image_url = img_el.get('src', '') if img_el else ''

                products.append({
                    'title': title[:200],
                    'price': price,
                    'currency': 'USD',
                    'rating': 0.0,
                    'reviews': 0,
                    'url': href,
                    'source': 'eBay',
                    'image_url': image_url,
                })

                if len(products) >= max_results:
                    break

            except Exception as e:
                logger.debug(f"Skipping eBay scraped item: {e}")
                continue

        logger.info(f"✅ eBay scrape: {len(products)} products for '{query}'")
        return products

    except Exception as e:
        logger.error(f"❌ eBay direct scraping failed: {e}")
        return []
