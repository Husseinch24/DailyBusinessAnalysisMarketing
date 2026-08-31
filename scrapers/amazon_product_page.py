import requests
import random
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

HEADERS_ROTATION = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_6) AppleWebKit/605.1.15 "
                      "(KHTML, like Gecko) Version/15 Safari/605.1.15",
        "Accept-Language": "en-US,en;q=0.9",
    },
]


def safe_text(el):
    return el.get_text(strip=True) if el else None


def extract_product_page(asin: str, marketplace="com"):
    """
    Scrapes ONLY the product detail page (stable).
    Does NOT scrape reviews.
    Returns JSON-ready dict or {} if blocked/failed.
    """
    url = f"https://www.amazon.{marketplace}/dp/{asin}"
    headers = random.choice(HEADERS_ROTATION)

    print(f"[product] Fetching product page for ASIN {asin}")

    try:
        r = requests.get(url, headers=headers, timeout=12)
    except Exception as e:
        print(f"[product] Request error: {e}")
        return {}

    if r.status_code != 200:
        print(f"[product] Blocked with HTTP {r.status_code}")
        return {}

    soup = BeautifulSoup(r.text, "html.parser")

    # Title
    title = safe_text(soup.select_one("#productTitle"))

    # Brand
    brand = safe_text(soup.select_one("#bylineInfo"))

    # Price
    price_tag = soup.select_one("#corePriceDisplay_desktop_feature_div span.a-offscreen")
    price = safe_text(price_tag)

    # Rating
    rating_tag = soup.select_one("i.a-icon-star span")
    rating = safe_text(rating_tag)

    # Total ratings count
    rating_count_tag = soup.select_one("#acrCustomerReviewText")
    rating_count = safe_text(rating_count_tag)

    # Bullet points
    bullets = [
        safe_text(li) for li in soup.select("#feature-bullets ul li")
        if safe_text(li)
    ]

    # Images
    image_tags = soup.select("#altImages img")
    images = [img.get("src") for img in image_tags if img.get("src")]

    # Sentiment (title + bullet points)
    sentiment_text = " ".join([title or ""] + bullets)
    sentiment = analyzer.polarity_scores(sentiment_text)["compound"]

    return {
        "asin": asin,
        "title": title,
        "brand": brand,
        "price": price,
        "rating": rating,
        "rating_count": rating_count,
        "bullets": bullets,
        "images": images,
        "sentiment_score": sentiment,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "product_page"
    }
