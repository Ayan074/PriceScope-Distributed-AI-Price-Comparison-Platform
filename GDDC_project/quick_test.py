"""Quick test of individual scrapers (without starting services)."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

async def test_ebay():
    print("\n=== Testing eBay Scraper ===")
    from services.ebay.scraper import search_ebay
    products = await search_ebay("wireless mouse", 3)
    print(f"Got {len(products)} products")
    for p in products:
        print(f"  {p['title'][:60]} | ${p['price']} | {p['source']}")
    return len(products) > 0

async def test_google():
    print("\n=== Testing Google Scraper (SerpAPI) ===")
    from services.google.scraper import search_google
    products = await search_google("wireless mouse", 3)
    print(f"Got {len(products)} products")
    for p in products:
        print(f"  {p['title'][:60]} | INR {p['price']} | {p['source']}")
    return len(products) > 0

async def test_walmart():
    print("\n=== Testing Walmart Scraper ===")
    from services.walmart.scraper import search_walmart
    products = await search_walmart("wireless mouse", 3)
    print(f"Got {len(products)} products")
    for p in products:
        print(f"  {p['title'][:60]} | ${p['price']} | {p['source']}")
    return len(products) > 0

async def main():
    print("Testing individual scrapers...\n")
    results = {}
    
    results['ebay'] = await test_ebay()
    results['google'] = await test_google()
    results['walmart'] = await test_walmart()
    
    print("\n" + "=" * 50)
    print("  RESULTS")
    print("=" * 50)
    for name, ok in results.items():
        status = "PASS" if ok else "No results (check SERPAPI_KEY)"
        icon = "+" if ok else "-"
        print(f"  [{icon}] {name}: {status}")
    
    passed = sum(1 for v in results.values() if v)
    print(f"\n  {passed}/{len(results)} sources working")
    print("  (Amazon requires Selenium + running service, tested separately)")

asyncio.run(main())
