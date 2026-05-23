"""Analyze eBay HTML to find product containers."""
import re
from bs4 import BeautifulSoup

html = open('debug_ebay.html', encoding='utf-8').read()
soup = BeautifulSoup(html, 'lxml')

# Find ALL li elements that contain both an /itm/ link and a price
print("=== LI elements with /itm/ links ===")
li_items = soup.find_all('li')
product_lis = []
for li in li_items:
    link = li.find('a', href=re.compile(r'/itm/'))
    price_el = li.find(string=re.compile(r'\$\d'))
    if link and price_el:
        classes = ' '.join(li.get('class', []))
        product_lis.append(li)
        if len(product_lis) <= 5:
            # Get text content
            title_text = link.get_text(strip=True)[:60] or 'N/A'
            price_text = price_el.strip()[:20]
            print(f"  li.{classes[:60]} | title: {title_text} | price: {price_text}")

print(f"\nTotal product LIs: {len(product_lis)}")

# Now let's look at the structure of the first product li
if product_lis:
    first = product_lis[0]
    classes = first.get('class', [])
    print(f"\nFirst product li classes: {classes}")
    
    # Find all child elements with their classes
    for child in first.find_all(True, recursive=False):
        child_classes = child.get('class', [])
        print(f"  <{child.name} class='{' '.join(child_classes)[:60]}'>")
        for gc in child.find_all(True, recursive=False):
            gc_classes = gc.get('class', [])
            text = gc.get_text(strip=True)[:40]
            print(f"    <{gc.name} class='{' '.join(gc_classes)[:60]}'> {text}")
