"""
Celery Tasks — One per data source.
Now updated to include Target Service.
"""

import logging
import httpx

from celery_app import app
from celery_app.circuit_breaker import breakers

logger = logging.getLogger(__name__)

# Microservice URLs (each service runs on its own port)
# ADDED: Target on port 8007
SERVICE_URLS = {
    'amazon':  'http://localhost:8005',
    'ebay':    'http://localhost:8003',
    'google':  'http://localhost:8004',
    'walmart': 'http://localhost:8006',
    'target':  'http://localhost:8007', 
}


def _fetch_from_service(source_name: str, query: str) -> list[dict]:
    """Generic helper: fetch product data from a microservice."""
    breaker = breakers.get(source_name)

    # Circuit breaker check
    if breaker and not breaker.can_execute():
        logger.warning(f"⚡ [{source_name}] Circuit is OPEN — skipping this source")
        return []

    try:
        url = SERVICE_URLS[source_name]
        # FIX: Increased timeout from 15.0 to 40.0 to accommodate slow Selenium scrapers
        with httpx.Client(timeout=40.0) as client:
            resp = client.get(f"{url}/search", params={"query": query})
            resp.raise_for_status()

        products = resp.json().get("products", [])
        logger.info(f"✅ [{source_name}] Celery task returned {len(products)} products")

        if breaker:
            breaker.record_success()

        return products

    except Exception as e:
        logger.error(f"❌ [{source_name}] Celery task failed: {e}")
        if breaker:
            breaker.record_failure()
        return []


# ─── Celery Task Definitions ─────────────────────────────────────────────────

@app.task(
    bind=True,
    name='celery_app.tasks.search_amazon_task',
    max_retries=2,
    default_retry_delay=2,
    acks_late=True,
)
def search_amazon_task(self, query: str) -> list[dict]:
    try:
        return _fetch_from_service('amazon', query)
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task(
    bind=True,
    name='celery_app.tasks.search_ebay_task',
    max_retries=2,
    default_retry_delay=2,
    acks_late=True,
)
def search_ebay_task(self, query: str) -> list[dict]:
    try:
        return _fetch_from_service('ebay', query)
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task(
    bind=True,
    name='celery_app.tasks.search_google_task',
    max_retries=2,
    default_retry_delay=2,
    acks_late=True,
)
def search_google_task(self, query: str) -> list[dict]:
    try:
        return _fetch_from_service('google', query)
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task(
    bind=True,
    name='celery_app.tasks.search_walmart_task',
    max_retries=2,
    default_retry_delay=2,
    acks_late=True,
)
def search_walmart_task(self, query: str) -> list[dict]:
    try:
        return _fetch_from_service('walmart', query)
    except Exception as exc:
        raise self.retry(exc=exc)

# NEW: Target Task Definition
@app.task(
    bind=True,
    name='celery_app.tasks.search_target_task',
    max_retries=2,
    default_retry_delay=2,
    acks_late=True,
)
def search_target_task(self, query: str) -> list[dict]:
    """Worker task: Search Target via its microservice (SerpAPI)."""
    try:
        return _fetch_from_service('target', query)
    except Exception as exc:
        logger.warning(f"[Target] Retrying... attempt {self.request.retries + 1}")
        raise self.retry(exc=exc)