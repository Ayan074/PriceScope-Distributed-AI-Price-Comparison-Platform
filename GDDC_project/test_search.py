"""
Test script — Verifies each microservice individually, then the full gateway pipeline.

Usage:
    1. Start all services: python run_all.py
    2. In another terminal: python test_search.py

Tests:
    - Amazon  (port 8005) — Selenium scraper
    - eBay    (port 8003) — Lightweight scraper
    - Google  (port 8004) — SerpAPI
    - Walmart (port 8006) — Scraping fallback
    - Gateway (port 8000) — Full distributed pipeline
"""

import asyncio
import time
import httpx


async def test_service(name: str, port: int, query: str) -> str:
    """Test a single microservice endpoint."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            start = time.time()

            if port == 8000:
                r = await client.post(
                    f"http://localhost:{port}/api/compare",
                    json={"query": query}
                )
            else:
                r = await client.get(
                    f"http://localhost:{port}/search",
                    params={"query": query}
                )

            elapsed = (time.time() - start) * 1000

            data = r.json()
            products = data.get("products", [])

            lines = [f"\n{'='*50}"]
            lines.append(f"  {name} (port {port}) — {len(products)} products in {elapsed:.0f}ms")
            lines.append(f"{'='*50}")

            if port == 8000:
                # Gateway response has extra info
                mode = data.get("processing_mode", "?")
                sources = data.get("sources_searched", [])
                lines.append(f"  Mode: {mode}")
                lines.append(f"  Sources: {', '.join(sources)}")
                if data.get("insights"):
                    lines.append(f"  Insights: {data['insights'][:200]}")

            for p in products[:5]:
                price_inr = p.get('normalized_price_inr', p.get('price', 0))
                lines.append(
                    f"  [{p.get('source', '?')}] "
                    f"{p.get('title', '')[:55]} | "
                    f"₹{price_inr:,.0f} | "
                    f"{p.get('rating', 0)}/5 "
                    f"({p.get('reviews', 0)} reviews)"
                )

            if not products:
                lines.append(f"  ⚠️ No products returned")

            return "\n".join(lines)

    except Exception as e:
        return f"\n  ❌ {name} (port {port}): ERROR — {e}"


async def test_health():
    """Test the health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("http://localhost:8000/api/health")
            data = r.json()

            lines = ["\n" + "=" * 50]
            lines.append("  HEALTH CHECK")
            lines.append("=" * 50)
            lines.append(f"  Gateway: {data.get('gateway', '?')}")
            lines.append(f"  Mode: {data.get('processing_mode', '?')}")

            for svc in data.get("services", []):
                status_icon = "✅" if svc["status"] == "healthy" else "❌"
                rt = f"{svc.get('response_time_ms', '?')}ms" if svc.get('response_time_ms') else "N/A"
                lines.append(f"  {status_icon} {svc['name']}: {svc['status']} ({rt})")

            # Circuit breakers
            cb = data.get("circuit_breakers", {})
            if cb:
                lines.append("\n  Circuit Breakers:")
                for name, info in cb.items():
                    lines.append(f"    {name}: {info.get('state', '?')} (failures: {info.get('failure_count', 0)})")

            return "\n".join(lines)

    except Exception as e:
        return f"\n  ❌ Health check failed: {e}"


async def main():
    query = "wireless mouse"

    print("\n" + "=" * 60)
    print("  🧪 PriceScope — Service Test Suite")
    print("=" * 60)
    print(f"\n  Search query: '{query}'")

    results = []

    # Health check first
    results.append(await test_health())

    # Test individual services
    services = [
        ("Amazon (Selenium)",  8005),
        ("eBay (Scraping)",    8003),
        ("Google (SerpAPI)",   8004),
        ("Walmart (Scraping)", 8006),
    ]

    for name, port in services:
        results.append(await test_service(name, port, query))

    # Test gateway (full pipeline)
    results.append(await test_service("Gateway (Full Pipeline)", 8000, query))

    # Write results
    output = "\n".join(results)
    print(output)

    with open("test_output.txt", "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n\n  ✅ Done! Results saved to test_output.txt\n")


if __name__ == "__main__":
    asyncio.run(main())
