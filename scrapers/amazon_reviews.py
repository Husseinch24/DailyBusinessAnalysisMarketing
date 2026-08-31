import requests
import random
import time
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

HEADERS_LIST = [
    {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
    {
        "User-Agent":
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17 Safari/605.1.15",
        "Accept-Language": "en-US,en;q=0.9",
    },
]


# ----------------------------------------------------------
# PARSE REVIEW HTML BLOCK
# ----------------------------------------------------------

def parse_review_card(card):
    """Extract a single Amazon review block."""

    title = card.select_one("a[data-hook='review-title']")
    body = card.select_one("span[data-hook='review-body']")
    rating_tag = card.select_one("i[data-hook='review-star-rating'] span")
    date_tag = card.select_one("span[data-hook='review-date']")
    helpful_tag = card.select_one("span[data-hook='helpful-vote-statement']")

    # Normalize rating: “5.0 out of 5 stars”
    rating = None
    if rating_tag:
        try:
            rating = float(rating_tag.get_text(strip=True).split()[0])
        except:
            rating = None

    # Normalize “Reviewed in the United States on January 3, 2024”
    timestamp = None
    if date_tag:
        text = date_tag.get_text(strip=True)
        try:
            text = text.split(" on ")[-1]
            timestamp = pd.to_datetime(text).isoformat()
        except:
            timestamp = datetime.utcnow().isoformat() + "Z"

    # Normalize helpful votes
    helpful = 0
    if helpful_tag:
        raw = helpful_tag.get_text(strip=True).lower()
        if "one" in raw:
            helpful = 1
        elif raw[0].isdigit():
            helpful = int(raw.split()[0])

    return {
        "review_title": title.get_text(strip=True) if title else None,
        "text": body.get_text(strip=True) if body else None,
        "rating": rating,
        "timestamp": timestamp,
        "helpful_vote": helpful,
    }


# ----------------------------------------------------------
# SCRAPE REVIEWS (WITH PAGINATION)
# ----------------------------------------------------------

def scrape_amazon_reviews(asin: str, max_reviews=20, marketplace="com"):
    """
    Scrape Amazon customer reviews for a given ASIN.

    Returns list[dict] matching the ingestion schema.
    Fails safely (returns empty list if blocked).
    """

    print(f"[reviews] Fetching reviews for ASIN {asin}")

    reviews = []
    page = 1

    while len(reviews) < max_reviews and page <= 5:  # scrape max 5 pages
        url = (
            f"https://www.amazon.{marketplace}/product-reviews/{asin}"
            f"/?pageNumber={page}"
        )
        headers = random.choice(HEADERS_LIST)
        time.sleep(random.uniform(1, 2.5))  # anti-block

        try:
            r = requests.get(url, headers=headers, timeout=12)
        except Exception as e:
            print(f"[reviews] Request failed: {e}")
            break

        if r.status_code != 200:
            print(f"[reviews] HTTP {r.status_code} for page {page}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("div[data-hook='review']")

        if not cards:
            print(f"[reviews] No review blocks found on page {page}")
            break

        for card in cards:
            parsed = parse_review_card(card)
            if not parsed["text"]:
                continue  # invalid block

            sentiment = analyzer.polarity_scores(parsed["text"])["compound"]

            reviews.append({
                "asin": asin,
                "parent_asin": asin,
                "rating": parsed["rating"],
                "title": parsed["review_title"],
                "text": parsed["text"],
                "sentiment_score": sentiment,
                "helpful_vote": parsed["helpful_vote"],
                "verified_purchase": False,  # can be updated if needed
                "user_id": None,
                "timestamp": parsed["timestamp"],
                "source": "scraped"
            })

            if len(reviews) >= max_reviews:
                break

        page += 1

    print(f"[reviews] Collected {len(reviews)} reviews for ASIN {asin}")
    return reviews