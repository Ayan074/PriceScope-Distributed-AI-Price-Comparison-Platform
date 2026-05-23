"""
Walmart Product Scraper — SerpAPI primary + Direct scraping fallback.

General-purpose (works for any product, not category-specific).

Strategy:
    1. PRIMARY: SerpAPI 'walmart' engine (reliable, structured JSON)
    2. FALLBACK: Direct HTTP scraping of walmart.com search page
    3. If both fail → return [] (fault tolerance)

Prices are in USD, converted to INR by the gateway normalizer.
"""

import os
import re
import json
import logging
from dotenv import load_dotenv

import httpx
from bs4 import BeautifulSoup

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# Browser-like headers for direct scraping
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
}


async def search_walmart(query: str, max_results: int = 8) -> list[dict]:
    """
    Search Walmart: try SerpAPI first, then direct scraping, then give up.
    """
    # Method 1: SerpAPI (most reliable)
    products = await _search_walmart_serpapi(query, max_results)
    if products:
        return products

    # Method 2: Direct scraping (fallback)
    products = await _search_walmart_scrape(query, max_results)
    if products:
        return products

    logger.warning(f"⚠️ Walmart: both methods failed for '{query}'")
    return []


async def _search_walmart_serpapi(query: str, max_results: int = 8) -> list[dict]:
    """Search Walmart via SerpAPI walmart engine."""
    if not SERPAPI_KEY:
        logger.info("No SERPAPI_KEY set, skipping SerpAPI for Walmart")
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "engine": "walmart",
        "query": query,
        "api_key": SERPAPI_KEY,
    }

    logger.info(f"🔍 Trying SerpAPI Walmart for: '{query}'")

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

                # Price extraction
                price_val = 0.0
                if "primary_offer" in item:
                    offer = item["primary_offer"]
                    price_val = float(offer.get("offer_price", 0))
                elif "price" in item:
                    p = item["price"]
                    if isinstance(p, (int, float)):
                        price_val = float(p)
                    elif isinstance(p, str):
                        match = re.search(r'[\d.]+', p.replace(',', ''))
                        if match:
                            price_val = float(match.group())

                if price_val <= 0:
                    continue

                # Rating
                rating = float(item.get("rating", 0.0))
                reviews = int(item.get("reviews", 0))

                products.append({
                    "title": title[:200],
                    "price": price_val,
                    "currency": "USD",
                    "rating": min(rating, 5.0),
                    "reviews": reviews,
                    "url": item.get("product_page_url", item.get("link", "")),
                    "source": "Walmart",
                    "image_url": item.get("thumbnail", ""),
                })
            except Exception as e:
                logger.debug(f"Skipping Walmart SerpAPI item: {e}")
                continue

        logger.info(f"✅ SerpAPI Walmart: {len(products)} products for '{query}'")
        return products

    except Exception as e:
        logger.error(f"❌ SerpAPI Walmart failed: {e}")
        return []


async def _search_walmart_scrape(query: str, max_results: int = 8) -> list[dict]:
    """
    Direct scraping fallback for Walmart.
    Walmart uses Next.js, so product data is embedded in __NEXT_DATA__ JSON.
    """
    search_url = f"https://www.walmart.com/search?q={query.replace(' ', '+')}"

    logger.info(f"🔍 Trying direct Walmart scraping for: '{query}'")

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(search_url, headers=HEADERS)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'lxml')

        # Method A: Try __NEXT_DATA__ JSON (most reliable for Next.js sites)
        script_tag = soup.find('script', id='__NEXT_DATA__')
        if script_tag:
            try:
                next_data = json.loads(script_tag.string)
                items = _extract_from_next_data(next_data, max_results)
                if items:
                    logger.info(f"✅ Walmart scrape (__NEXT_DATA__): {len(items)} products")
                    return items
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"__NEXT_DATA__ parse failed: {e}")

        # Method B: Parse HTML product cards directly
        products = []
        product_cards = soup.select('[data-item-id], .search-result-gridview-item, [data-testid="list-view"]')

        for card in product_cards[:max_results + 4]:
            try:
                # Title
                title_el = card.select_one('[data-automation-id="product-title"], .product-title-link span, a span')
                title = title_el.get_text(strip=True) if title_el else ''
                if not title or len(title) < 3:
                    continue

                # Price
                price_el = card.select_one('[data-automation-id="product-price"] .f2, .price-main .visuallyhidden, [itemprop="price"]')
                if not price_el:
                    continue
                price_text = price_el.get_text(strip=True)
                price_match = re.search(r'([\d,]+\.?\d*)', price_text.replace(',', ''))
                if not price_match:
                    continue
                price = float(price_match.group(1))
                if price <= 0:
                    continue

                # URL
                link_el = card.select_one('a[href*="/ip/"]')
                url = ''
                if link_el:
                    href = link_el.get('href', '')
                    url = f"https://www.walmart.com{href}" if href.startswith('/') else href

                # Image
                img_el = card.select_one('img[data-testid="productTileImage"], img')
                image_url = img_el.get('src', '') if img_el else ''

                # Rating
                rating = 0.0
                star_el = card.select_one('[data-automation-id="product-ratings"] .f7, .stars-container')
                if star_el:
                    star_match = re.search(r'([\d.]+)', star_el.get_text())
                    if star_match:
                        rating = min(float(star_match.group(1)), 5.0)

                # Reviews
                reviews = 0
                review_el = card.select_one('[data-automation-id="product-ratings"] .f7:last-child')
                if review_el:
                    rev_match = re.search(r'(\d+)', review_el.get_text().replace(',', ''))
                    if rev_match:
                        reviews = int(rev_match.group(1))

                products.append({
                    'title': title[:200],
                    'price': price,
                    'currency': 'USD',
                    'rating': rating,
                    'reviews': reviews,
                    'url': url,
                    'source': 'Walmart',
                    'image_url': image_url,
                })

                if len(products) >= max_results:
                    break

            except Exception as e:
                logger.debug(f"Skipping Walmart HTML item: {e}")
                continue

        logger.info(f"✅ Walmart scrape (HTML): {len(products)} products")
        return products

    except Exception as e:
        logger.error(f"❌ Walmart direct scraping failed: {e}")
        return []


def _extract_from_next_data(next_data: dict, max_results: int) -> list[dict]:
    """Extract products from Walmart's __NEXT_DATA__ JSON structure."""
    products = []

    try:
        # Navigate the nested structure
        # Walmart's structure: props.pageProps.initialData.searchResult.itemStacks[0].items
        page_props = next_data.get('props', {}).get('pageProps', {})
        initial_data = page_props.get('initialData', {})
        search_result = initial_data.get('searchResult', {})
        item_stacks = search_result.get('itemStacks', [])

        items = []
        for stack in item_stacks:
            items.extend(stack.get('items', []))

        for item in items[:max_results + 4]:
            try:
                if item.get('__typename') == 'Product' or 'name' in item:
                    title = item.get('name', '')
                    if not title:
                        continue

                    price = float(item.get('price', 0) or item.get('priceInfo', {}).get('currentPrice', {}).get('price', 0))
                    if price <= 0:
                        continue

                    rating = float(item.get('averageRating', 0))
                    reviews = int(item.get('numberOfReviews', 0))

                    products.append({
                        'title': title[:200],
                        'price': price,
                        'currency': 'USD',
                        'rating': min(rating, 5.0),
                        'reviews': reviews,
                        'url': f"https://www.walmart.com{item.get('canonicalUrl', '')}",
                        'source': 'Walmart',
                        'image_url': item.get('imageInfo', {}).get('thumbnailUrl', item.get('image', '')),
                    })

                    if len(products) >= max_results:
                        break
            except Exception:
                continue

    except Exception as e:
        logger.debug(f"__NEXT_DATA__ extraction error: {e}")

    return products
