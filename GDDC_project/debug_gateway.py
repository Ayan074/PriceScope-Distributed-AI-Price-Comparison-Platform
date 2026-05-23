"""Debug the gateway."""
import httpx

# Raw request to gateway
try:
    r = httpx.get("http://localhost:8000/api/health", timeout=10.0)
    print(f"Status: {r.status_code}")
    print(f"Headers: {dict(r.headers)}")
    print(f"Body (first 500): {r.text[:500]}")
except Exception as e:
    print(f"Request error: {e}")

# Check the root
print("\n--- Root ---")
try:
    r = httpx.get("http://localhost:8000/", timeout=10.0)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type')}")
    print(f"Body: {r.text[:200]}")
except Exception as e:
    print(f"Root error: {e}")

# Check docs
print("\n--- Docs ---")
try:
    r = httpx.get("http://localhost:8000/docs", timeout=10.0)
    print(f"Status: {r.status_code}")
except Exception as e:
    print(f"Docs error: {e}")
