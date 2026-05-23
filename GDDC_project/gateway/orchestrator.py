"""
Orchestrator — Coordinates the full product comparison pipeline.

This is the CORE of the distributed architecture. It supports TWO execution modes:

MODE 1: CELERY (Distributed Task Queue)
    - Dispatches search tasks to Celery workers via group()
    - Each worker runs in a separate OS process (true multiprocessing)
    - Tasks are routed to dedicated queues (amazon, ebay, google, walmart)
    - Results collected with timeout for fault tolerance

MODE 2: ASYNC PARALLEL (Fallback when Redis/Celery unavailable)
    - Uses asyncio.gather() + ThreadPoolExecutor for parallel HTTP calls
    - Still achieves parallelism via Python's concurrent.futures
    - Automatic fallback — no manual configuration needed

Both modes include:
    - Circuit breaker checks before dispatching
    - Graceful degradation (partial results if some sources fail)
    - Result normalization, deduplication, and ranking
    - In-memory caching with optional Redis
"""

import json
import asyncio
import logging
import time
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import httpx

from gateway.config import settings
from gateway.llm_engine import analyze_with_rules, run_mcp_agent
from shared.utils import (
    normalize_title,
    convert_to_inr,
    calculate_value_score,
    deduplicate_products,
)
from shared.cache import (
    cache_get_json,
    cache_set_json,
    make_cache_key,
    add_to_search_history,
)
from celery_app.circuit_breaker import breakers

logger = logging.getLogger(__name__)

_http_client: Optional[httpx.AsyncClient] = None
_executor = ThreadPoolExecutor(max_workers=4)

# Track whether Celery is available
_celery_available: Optional[bool] = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        # FIX: Increased global HTTP timeout to 45s
        _http_client = httpx.AsyncClient(timeout=45.0)
    return _http_client


def _check_celery_available() -> bool:
    """Check if Celery + Redis is available for distributed task dispatch."""
    global _celery_available

    if _celery_available is not None:
        return _celery_available

    if not settings.USE_CELERY:
        _celery_available = False
        logger.info("⚙️ Celery disabled via USE_CELERY=false, using async parallel mode")
        return False

    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_timeout=2)
        r.ping()
        _celery_available = True
        logger.info("✅ Redis is available — using Celery distributed task queue")
        return True
    except Exception as e:
        _celery_available = False
        logger.info(f"⚠️ Redis not available ({e}) — falling back to async parallel mode")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  MODE 1: CELERY DISTRIBUTED DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

def _dispatch_celery(query: str) -> list[dict]:
    """
    Dispatch search tasks to Celery workers using group() for parallel execution.
    Each task runs in a separate worker process → true multiprocessing.
    """
    from celery import group
    from celery_app.tasks import (
        search_amazon_task,
        search_ebay_task,
        search_google_task,
        search_walmart_task,
        search_target_task,  # <--- ADD THIS
    )

    task_map = {
        'amazon': search_amazon_task,
        'ebay': search_ebay_task,
        'google': search_google_task,
        'walmart': search_walmart_task,
        'target': search_target_task,
    }

    # Build task group, skipping sources with open circuit breakers
    tasks = []
    source_order = []

    for source_name, task_fn in task_map.items():
        breaker = breakers.get(source_name)
        if breaker and not breaker.can_execute():
            logger.warning(f"⚡ Skipping {source_name} — circuit breaker OPEN")
            continue
        tasks.append(task_fn.s(query))
        source_order.append(source_name)

    if not tasks:
        logger.error("All circuit breakers are OPEN! No sources available.")
        return []

    logger.info(f"🚀 Dispatching Celery group: {source_order}")

    # Execute all tasks in parallel via Celery group
    job = group(tasks)
    result = job.apply_async()

    # Collect results with timeout (fault tolerance)
    try:
        # FIX: Hardcoded to 45.0 to give enough time for both Amazon AND eBay 
        # to finish sequentially on the single worker.
        results = result.get(
            timeout=45.0,
            propagate=False
        )
    except Exception as e:
        logger.error(f"❌ Celery group timed out or failed: {e}")
        # Try to get whatever results completed
        results = []
        for async_result in result.results:
            try:
                r = async_result.get(timeout=1, propagate=False)
                results.append(r)
            except Exception:
                results.append([])

    # Flatten results
    all_products = []
    for i, res in enumerate(results):
        source = source_order[i] if i < len(source_order) else "unknown"
        if isinstance(res, list):
            all_products.extend(res)
            logger.info(f"  ✅ {source}: {len(res)} products")
        elif isinstance(res, Exception):
            logger.error(f"  ❌ {source}: task failed — {res}")
        else:
            logger.warning(f"  ⚠️ {source}: unexpected result type {type(res)}")

    return all_products


# ══════════════════════════════════════════════════════════════════════════════
#  MODE 2: ASYNC PARALLEL FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_from_service(service_name: str, service_url: str, query: str) -> list[dict]:
    """Fetch products from a single microservice with retry + circuit breaker."""
    source_key = service_name.lower()
    breaker = breakers.get(source_key)

    if breaker and not breaker.can_execute():
        logger.warning(f"⚡ Skipping {service_name} — circuit breaker OPEN")
        return []

    retries = 2
    for attempt in range(retries + 1):
        try:
            client = get_http_client()
            start = time.time()
            response = await client.get(
                f"{service_url}/search",
                params={"query": query},
                timeout=45.0,  # FIX: Increased async timeout to 45s
            )
            elapsed = (time.time() - start) * 1000
            response.raise_for_status()
            data = response.json()
            products = data.get("products", [])
            logger.info(f"✅ {service_name}: {len(products)} products in {elapsed:.0f}ms")
            if breaker:
                breaker.record_success()
            return products

        except httpx.ConnectError:
            logger.warning(f"⚠️ {service_name} not reachable (attempt {attempt + 1})")
        except httpx.TimeoutException:
            logger.warning(f"⏱️ {service_name} timeout (attempt {attempt + 1})")
        except Exception as e:
            logger.error(f"❌ {service_name} error: {e}")

        await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff

    if breaker:
        breaker.record_failure()
    logger.error(f"❌ {service_name} failed after {retries + 1} attempts")
    return []


async def _dispatch_async_parallel(query: str) -> list[dict]:
    """Async parallel dispatch to all microservices using asyncio.gather()."""
    service_urls = settings.service_urls

    tasks = [
        _fetch_from_service(name, url, query)
        for name, url in service_urls.items()
    ]

    logger.info(f"🚀 Async parallel dispatch: {list(service_urls.keys())}")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_products = []
    for result in results:
        if isinstance(result, list):
            all_products.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"Task exception: {result}")

    return all_products


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def normalize_products(products: list[dict]) -> list[dict]:
    """Normalize all products: clean titles, convert to INR, compute value scores."""
    normalized = []
    for product in products:
        product["title"] = normalize_title(product.get("title", ""))

        price = float(product.get("price", 0))
        currency = product.get("currency", "INR")
        product["price"] = price
        product["normalized_price_inr"] = convert_to_inr(price, currency)

        rating = float(product.get("rating", 0))
        reviews = int(product.get("reviews", 0))
        product["value_score"] = calculate_value_score(
            product["normalized_price_inr"], rating, reviews
        )

        normalized.append(product)

    return deduplicate_products(normalized)


def rank_products(products: list[dict]) -> dict:
    """
    The 'Sir-Pleaser' Ranking Logic.
    Uses Price Clustering to filter out accessories from the Winner Cards.
    """
    if not products:
        return {"best_price": None, "best_rating": None, "best_value": None}

    # 1. The 'No-Fly List' for accessories
    bad_keywords = ["cover", "case", "glass", "protector", "cable", "strap", "lens", "adapter", "for samsung", "for iphone"]
    
    # 2. Filter by Keyword
    filtered_by_name = [
        p for p in products 
        if not any(word in p.get("title", "").lower() for word in bad_keywords)
    ]

    # 3. Filter by Price Gap (Clustering)
    if filtered_by_name:
        prices = [p.get("normalized_price_inr", 0) for p in filtered_by_name if p.get("normalized_price_inr", 0) > 0]
        if prices:
            avg_price = sum(prices) / len(prices)
            # Anything less than 30% of the average is probably an accessory that missed the keyword filter
            price_floor = avg_price * 0.3
            valid_products = [p for p in filtered_by_name if p.get("normalized_price_inr", 0) >= price_floor]
        else:
            valid_products = filtered_by_name
    else:
        valid_products = products

    # 4. Fallback if we filtered everything
    if not valid_products:
        valid_products = products

    # 5. Determine Winners
    best_price = min(valid_products, key=lambda p: p.get("normalized_price_inr", float("inf")))
    best_rating = max(valid_products, key=lambda p: (float(p.get("rating", 0.0)), int(p.get("reviews", 0))))
    best_value = max(valid_products, key=lambda p: float(p.get("value_score", 0.0)))

    return {
        "best_price": best_price,
        "best_rating": best_rating,
        "best_value": best_value,
    }


async def compare_products(query: str) -> dict:
    """
    Full comparison pipeline:
    1. Check cache
    2. Dispatch to all sources (Celery or async parallel)
    3. Normalize + deduplicate + rank
    4. Generate insights
    5. Cache results
    6. Return
    """
    start_time = time.time()

    # ── Cache check ──
    cache_key = make_cache_key("compare", query)
    cached = cache_get_json(cache_key)
    if cached:
        logger.info(f"🎯 Cache hit: {query}")
        cached["cached"] = True
        return cached

    logger.info(f"🔍 Starting comparison: '{query}'")

    # ── Dispatch to all sources ──
    use_celery = _check_celery_available()

    if use_celery:
        # Mode 1: Celery distributed task queue
        logger.info("📡 Mode: CELERY (distributed workers)")
        loop = asyncio.get_event_loop()
        all_products = await loop.run_in_executor(_executor, _dispatch_celery, query)
    else:
        # Mode 2: Async parallel fallback
        logger.info("📡 Mode: ASYNC PARALLEL (direct HTTP)")
        all_products = await _dispatch_async_parallel(query)

    # ── Normalize + Rank ──
    normalized = normalize_products(all_products)
    rankings = rank_products(normalized)

    # ── Generate insights ──
    insights = None
    llm_used = False

    # 1. Try to use the AI Agent if we have an API key
    if getattr(settings, "has_openai_key", False) and getattr(settings, "OPENAI_API_KEY", None):
        logger.info("🧠 OpenAI API Key found, attempting MCP Agent...")
        try:
            mcp_result = await run_mcp_agent(query, settings.OPENAI_API_KEY)
            if mcp_result and "insights" in mcp_result:
                insights = mcp_result["insights"]
                llm_used = True
                logger.info("✅ AI Agent successfully generated insights!")
        except Exception as e:
            logger.error(f"⚠️ AI Agent failed, gracefully falling back: {e}")
            
    # 2. Fallback to Rule-Based Math if AI failed or is turned off
    if not insights:
        logger.info("🧮 Using rule-based fallback for insights.")
        insights = analyze_with_rules(
            query,
            normalized,
            rankings["best_price"],
            rankings["best_rating"],
            rankings["best_value"],
        )

    elapsed = (time.time() - start_time) * 1000

    

    # ── Build response ──
    response = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "products": normalized,
        "best_price": rankings["best_price"],
        "best_rating": rankings["best_rating"],
        "best_value": rankings["best_value"],
        "insights": insights,
        "total_results": len(normalized),
        "sources_searched": list(settings.service_urls.keys()),
        "cached": False,
        "llm_used": llm_used, # <--- Updates the UI dynamically!
        "processing_mode": "celery" if use_celery else "async_parallel",
        "processing_time_ms": round(elapsed, 1),
    }

    # ── Cache + History ──
    cache_set_json(cache_key, response, settings.CACHE_TTL_SECONDS)
    add_to_search_history(query, len(normalized))

    logger.info(f"✅ Comparison done in {elapsed:.0f}ms | {len(normalized)} products | mode: {'celery' if use_celery else 'async'}")

    return response


# ══════════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

async def check_service_health(service_name: str, service_url: str) -> dict:
    """Check if a single microservice is healthy."""
    try:
        client = get_http_client()
        start = time.time()
        response = await client.get(f"{service_url}/health", timeout=5.0)
        elapsed = (time.time() - start) * 1000

        source_key = service_name.lower()
        breaker = breakers.get(source_key)
        breaker_state = breaker.state if breaker else "N/A"

        return {
            "name": service_name,
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "url": service_url,
            "response_time_ms": round(elapsed, 1),
            "circuit_breaker": breaker_state,
        }
    except Exception:
        return {
            "name": service_name,
            "status": "unhealthy",
            "url": service_url,
            "response_time_ms": None,
            "circuit_breaker": breakers.get(service_name.lower(), None) and breakers[service_name.lower()].state,
        }


async def get_all_health() -> dict:
    """Health check for all services + infrastructure."""
    tasks = [
        check_service_health(name, url)
        for name, url in settings.service_urls.items()
    ]
    services = await asyncio.gather(*tasks)
    all_healthy = all(s["status"] == "healthy" for s in services)

    # Check processing mode
    celery_active = _check_celery_available()

    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": list(services),
        "gateway": "healthy",
        "processing_mode": "celery" if celery_active else "async_parallel",
        "circuit_breakers": {name: b.get_status() for name, b in breakers.items()},
    }