# scrapers/amazon_product.py

import random
from datetime import datetime
from typing import Dict, Any, Optional, List

import requests
from bs4 import BeautifulSoup


HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17 Safari/605.1.15",
        "Accept-Language": "en-US,en;q=0.9",
    },
]


def _clean_text(node) -> Optional[str]:
    if not node:
        return None
    txt = node.get_text(" ", strip=True)
    return txt if txt else None


def _parse_float_from_text(txt: Optional[str]) -> Optional[float]:
    if txt is None:
        return None
    txt = txt.replace("out of 5 stars", "").replace("$", "").replace(",", "").strip()
    if not txt:
        return None
    try:
        return float(txt.split()[0])
    except Exception:
        return None


def _parse_int_from_text(txt: Optional[str]) -> Optional[int]:
    if txt is None:
        return None
    txt = txt.replace("ratings", "").replace("rating", "").replace(",", "").strip()
    if not txt:
        return None
    parts = txt.split()
    try:
        return int(parts[0])
    except Exception:
        return None


def _extract_bullets(soup: BeautifulSoup) -> List[str]:
    bullets = []
    for li in soup.select("#feature-bullets ul li span.a-list-item"):
        t = _clean_text(li)
        if t:
            bullets.append(t)
    return bullets


def fetch_amazon_product(asin: str, marketplace: str = "com") -> Dict[str, Any]:
    """
    Scrape core details from an Amazon product page:
    - asin, title, brand
    - rating, rating_count
    - price
    - bullets (features)
    - timestamp, source

    Returns a single dict. On error, returns a minimal dict with asin + timestamp.
    """

    url = f"https://www.amazon.{marketplace}/dp/{asin}"
    headers = random.choice(HEADERS_LIST)

    print(f"[product] Fetching product page for ASIN {asin}")

    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        print(f"[product] ERROR fetching ASIN {asin}: {e}")
        return {"asin": asin, "timestamp": datetime.utcnow().isoformat() + "Z", "source": "product_scraper"}

    if resp.status_code != 200:
        print(f"[product] HTTP {resp.status_code} for ASIN {asin}")
        return {"asin": asin, "timestamp": datetime.utcnow().isoformat() + "Z", "source": "product_scraper"}

    soup = BeautifulSoup(resp.text, "html.parser")

    title = _clean_text(soup.select_one("#productTitle"))
    brand = _clean_text(soup.select_one("#bylineInfo"))
    rating_txt = _clean_text(soup.select_one("span[data-hook='rating-out-of-text']"))
    rating_count_txt = _clean_text(soup.select_one("#acrCustomerReviewText"))
    price_tag = soup.select_one("span.a-price span.a-offscreen")

    rating = _parse_float_from_text(rating_txt)
    rating_count = _parse_int_from_text(rating_count_txt)
    price = _parse_float_from_text(_clean_text(price_tag))

    bullets = _extract_bullets(soup)

    result: Dict[str, Any] = {
        "asin": asin,
        "title": title,
        "brand": brand,
        "rating": rating,
        "rating_count": rating_count,
        "price": price,
        "bullets": bullets,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "product_scraper",
    }

    return result