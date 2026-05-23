"""
Amazon Product Scraper — Selenium-based.

Uses headless Chrome via Selenium to scrape Amazon.in search results.
This bypasses API restrictions since Amazon's Product API is restricted to affiliates.

How it works:
    1. Launch headless Chrome with anti-detection flags
    2. Navigate to Amazon.in/s?k=<query>
    3. Wait for search results to load
    4. Parse the HTML with BeautifulSoup
    5. Extract: title, price (INR), rating, reviews, URL, image
    6. Return standardized product list

Fault tolerance:
    - If Chrome isn't installed → returns []
    - If Amazon blocks the request → returns []
    - If any product parsing fails → skips that product, continues others
    - Always cleans up the browser driver in finally block
"""

import re
import logging
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool for running synchronous Selenium in async FastAPI
_executor = ThreadPoolExecutor(max_workers=2)


def _create_driver():
    """Create a stealth headless Chrome driver."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    )

    # Suppress Selenium logs
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    options.add_experimental_option('useAutomationExtension', False)

    # Auto-download matching ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Remove navigator.webdriver flag (anti-detection)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, "webdriver", {get: () => undefined});
            window.chrome = { runtime: {} };
        '''
    })

    return driver


def search_amazon_sync(query: str, max_results: int = 8) -> list[dict]:
    """
    Synchronous Amazon scraper using Selenium + BeautifulSoup.
    Called from async context via ThreadPoolExecutor.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from bs4 import BeautifulSoup

    driver = None
    try:
        logger.info(f"🚀 Launching Selenium for Amazon search: '{query}'")
        driver = _create_driver()

        # Navigate to Amazon India search
        search_url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
        driver.get(search_url)

        # Wait for search results to appear (up to 10 seconds)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-component-type='s-search-result']")
            )
        )

        # Parse with BeautifulSoup for cleaner extraction
        soup = BeautifulSoup(driver.page_source, 'lxml')
        result_items = soup.select("[data-component-type='s-search-result']")

        logger.info(f"📦 Found {len(result_items)} raw Amazon results, parsing top {max_results}...")

        products = []
        for item in result_items[:max_results + 10]:  # Extra to account for sponsored/skipped
            try:
                # ── Title ──
                title_el = item.select_one('h2 a span, h2 span, .a-size-medium, .a-size-base-plus')
                title = title_el.get_text(strip=True) if title_el else ''
                if not title or len(title) < 5:
                    continue

                # ── URL ──
                url = ''
                for a_tag in item.find_all('a', href=True):
                    href = a_tag['href']
                    if '/dp/' in href or '/gp/' in href or (href.startswith('/') and 'javascript' not in href):
                        url = f"https://www.amazon.in{href}" if href.startswith('/') else href
                        if '?' in url and '/dp/' in url:
                            url = url.split('?')[0] 
                        break
                
                if not url:
                    # Fallback URL
                    url_el = item.select_one('h2 a')
                    if url_el and url_el.get('href'):
                        href = url_el['href']
                        url = f"https://www.amazon.in{href}" if href.startswith('/') else href
                    else:
                        continue  # Skip if we truly have no URL

                # ── Price ──
                price_el = item.select_one('.a-price .a-offscreen, .a-price-whole')
                if not price_el:
                    continue

                price_text = price_el.get_text(strip=True)
                # Strip out ₹, commas, and grab the numbers
                price_clean = price_text.replace('₹', '').replace(',', '').split('.')[0].strip()
                price_match = re.search(r'(\d+)', price_clean)
                if not price_match:
                    continue
                
                price = float(price_match.group(1))
                if price <= 0:
                    continue

                # ── Rating ──
                rating = 0.0
                rating_el = item.select_one('.a-icon-star-small .a-icon-alt, .a-icon-star .a-icon-alt')
                if rating_el:
                    rating_match = re.search(r'([\d.]+)', rating_el.get_text())
                    if rating_match:
                        rating = min(float(rating_match.group(1)), 5.0)

                # ── Reviews Count ──
                reviews = 0
                review_el = item.select_one('span[aria-label*="ratings"], a[href*="#customerReviews"] span, .s-underline-text')
                if review_el:
                    review_text = review_el.get_text(strip=True).replace(',', '')
                    review_match = re.search(r'(\d+)', review_text)
                    if review_match:
                        reviews = int(review_match.group(1))

                # ── Image ──
                img_el = item.select_one('.s-image')
                image_url = img_el['src'] if img_el and img_el.get('src') else ''

                products.append({
                    'title': title[:200],
                    'price': price,
                    'currency': 'INR',
                    'rating': rating,
                    'reviews': reviews,
                    'url': url,
                    'source': 'Amazon',
                    'image_url': image_url,
                })

                if len(products) >= max_results:
                    break

            except Exception as e:
                logger.debug(f"Skipping Amazon product: {e}")
                continue

        logger.info(f"✅ Amazon Selenium scraper: {len(products)} products for '{query}'")
        return products

    except Exception as e:
        logger.error(f"❌ Amazon Selenium scraper failed: {e}")
        return []

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


async def search_amazon(query: str, max_results: int = 8) -> list[dict]:
    """
    Async wrapper for the synchronous Selenium scraper.
    Runs in a ThreadPoolExecutor so it doesn't block the FastAPI event loop.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, search_amazon_sync, query, max_results)