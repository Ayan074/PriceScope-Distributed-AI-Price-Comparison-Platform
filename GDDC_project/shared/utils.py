"""
Shared utility functions for data normalization, currency conversion,
and value scoring.
"""

import re
from typing import Optional


# Static exchange rates (approximate, for demonstration)
EXCHANGE_RATES_TO_INR = {
    "INR": 1.0,
    "USD": 85.50,
    "EUR": 92.30,
    "GBP": 108.00,
}


def normalize_price(price_str: str) -> Optional[float]:
    """
    Extract numeric price from strings like '₹72,999', '$999.00', '72999'.
    Returns float or None if unparseable.
    """
    if isinstance(price_str, (int, float)):
        return float(price_str)

    if not price_str:
        return None

    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[₹$€£,\s]', '', str(price_str))

    # Extract the first number (with optional decimal)
    match = re.search(r'(\d+\.?\d*)', cleaned)
    if match:
        return float(match.group(1))

    return None


def normalize_title(title: str) -> str:
    """Clean product titles: remove extra whitespace, normalize casing."""
    if not title:
        return ""

    # Remove excessive whitespace
    cleaned = re.sub(r'\s+', ' ', title.strip())

    # Remove common noise patterns
    noise_patterns = [
        r'\(Renewed\)',
        r'\[.*?\]',
        r'FREE SHIPPING',
        r'Best Seller',
        r'Limited Time Deal',
    ]
    for pattern in noise_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


def convert_to_inr(price: float, currency: str) -> float:
    """Convert a price to INR using static exchange rates."""
    rate = EXCHANGE_RATES_TO_INR.get(currency.upper(), 1.0)
    return round(price * rate, 2)


def calculate_value_score(price: float, rating: float, reviews: int) -> float:
    """
    Advanced Value Scoring Formula.
    Balances Price, Rating, and Popularity.
    """
    if price <= 0:
        return 0.0
    
    # 1. Price Score: Lower price is better, but we use a log scale to prevent 
    # ultra-cheap items (cases) from breaking the math.
    price_factor = 100000 / (price + 100) 
    
    # 2. Trust Factor: Rating + log of reviews (more reviews = more trust)
    import math
    trust_score = (rating * 20) + (math.log10(reviews + 1) * 10)
    
    # 3. Final Score
    return round((price_factor * 0.4) + (trust_score * 0.6), 2)


def deduplicate_products(products: list[dict]) -> list[dict]:
    """
    Remove near-duplicate products based on normalized title similarity.
    Keeps the one with the lower price when duplicates are found within the same platform.
    """
    seen = {}
    unique = []

    for product in products:
        # Create a simplified key from title
        title_key = re.sub(r'[^a-z0-9]', '', product.get("title", "").lower())[:50]
        source = product.get("source", "")
        key = f"{source}:{title_key}"

        if key not in seen:
            seen[key] = product
            unique.append(product)
        else:
            # Keep the cheaper one
            existing_price = seen[key].get("normalized_price_inr", float("inf"))
            new_price = product.get("normalized_price_inr", float("inf"))
            if new_price < existing_price:
                # Replace in the unique list
                idx = unique.index(seen[key])
                unique[idx] = product
                seen[key] = product

    return unique


def group_similar_products(products: list[dict]) -> list[list[dict]]:
    """
    Group products that appear to be the same item across different platforms.
    Uses simple keyword matching on normalized titles.
    """
    if not products:
        return []

    groups: list[list[dict]] = []
    used = set()

    for i, p1 in enumerate(products):
        if i in used:
            continue

        group = [p1]
        used.add(i)

        title1_words = set(re.findall(r'\w+', p1.get("title", "").lower()))

        for j, p2 in enumerate(products):
            if j in used:
                continue
            if p1.get("source") == p2.get("source"):
                continue  # Same platform, skip

            title2_words = set(re.findall(r'\w+', p2.get("title", "").lower()))

            # Calculate Jaccard similarity
            if title1_words and title2_words:
                intersection = title1_words & title2_words
                union = title1_words | title2_words
                similarity = len(intersection) / len(union)

                if similarity > 0.35:  # Threshold for "same product"
                    group.append(p2)
                    used.add(j)

        groups.append(group)

    return groups
