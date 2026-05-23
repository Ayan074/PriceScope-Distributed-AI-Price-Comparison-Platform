"""Check service health."""
import httpx
import json

try:
    r = httpx.get("http://localhost:8000/api/health", timeout=10.0)
    data = r.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Gateway error: {e}")
    # Try individual services
    for name, port in [("Amazon", 8005), ("eBay", 8003), ("Google", 8004), ("Walmart", 8006), ("Gateway", 8000)]:
        try:
            r = httpx.get(f"http://localhost:{port}/health", timeout=3.0)
            print(f"  {name} ({port}): {r.status_code} - {r.json()}")
        except Exception as ex:
            print(f"  {name} ({port}): DOWN - {ex}")
