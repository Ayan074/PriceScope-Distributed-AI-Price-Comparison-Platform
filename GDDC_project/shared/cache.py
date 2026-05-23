"""
Caching layer with Redis support and in-memory fallback.
Provides transparent caching regardless of whether Redis is available.
"""

import json
import hashlib
import time
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

# In-memory fallback cache
_memory_cache: dict[str, dict[str, Any]] = {}
_redis_client = None
_redis_available = False


def _get_redis():
    """Try to connect to Redis, fall back to in-memory cache."""
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client

    try:
        import redis
        import os
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        client.ping()
        _redis_client = client
        _redis_available = True
        logger.info("✅ Connected to Redis")
        return client
    except Exception as e:
        logger.info(f"⚠️  Redis not available ({e}), using in-memory cache")
        _redis_available = False
        return None


def make_cache_key(prefix: str, query: str) -> str:
    """Generate a consistent cache key from a prefix and query string."""
    query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]
    return f"{prefix}:{query_hash}"


def cache_get(key: str) -> Optional[str]:
    """Get a value from cache. Returns None if not found or expired."""
    redis_client = _get_redis()

    if redis_client:
        try:
            return redis_client.get(key)
        except Exception:
            pass

    # In-memory fallback
    if key in _memory_cache:
        entry = _memory_cache[key]
        if entry["expires_at"] > time.time():
            return entry["value"]
        else:
            del _memory_cache[key]
    return None


def cache_set(key: str, value: str, ttl_seconds: int = 300) -> None:
    """Set a value in cache with TTL (default 5 minutes)."""
    redis_client = _get_redis()

    if redis_client:
        try:
            redis_client.setex(key, ttl_seconds, value)
            return
        except Exception:
            pass

    # In-memory fallback
    _memory_cache[key] = {
        "value": value,
        "expires_at": time.time() + ttl_seconds
    }


def cache_get_json(key: str) -> Optional[Any]:
    """Get and deserialize JSON from cache."""
    raw = cache_get(key)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def cache_set_json(key: str, data: Any, ttl_seconds: int = 300) -> None:
    """Serialize to JSON and store in cache."""
    cache_set(key, json.dumps(data, default=str), ttl_seconds)


def get_search_history(limit: int = 10) -> list[dict]:
    """Retrieve recent search history."""
    redis_client = _get_redis()

    if redis_client:
        try:
            history = redis_client.lrange("search_history", 0, limit - 1)
            return [json.loads(h) for h in history]
        except Exception:
            pass

    # In-memory fallback
    history_key = "__search_history__"
    if history_key in _memory_cache:
        items = _memory_cache[history_key].get("value", "[]")
        return json.loads(items)[:limit]
    return []


def add_to_search_history(query: str, result_count: int) -> None:
    """Add a search to history."""
    import datetime
    entry = json.dumps({
        "query": query,
        "result_count": result_count,
        "timestamp": datetime.datetime.now().isoformat()
    })

    redis_client = _get_redis()

    if redis_client:
        try:
            redis_client.lpush("search_history", entry)
            redis_client.ltrim("search_history", 0, 49)  # Keep last 50
            return
        except Exception:
            pass

    # In-memory fallback
    history_key = "__search_history__"
    if history_key not in _memory_cache:
        _memory_cache[history_key] = {"value": "[]", "expires_at": float("inf")}

    items = json.loads(_memory_cache[history_key]["value"])
    items.insert(0, json.loads(entry))
    items = items[:50]
    _memory_cache[history_key]["value"] = json.dumps(items)
