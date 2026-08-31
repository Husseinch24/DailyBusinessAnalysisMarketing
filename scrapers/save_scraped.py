import pandas as pd
from pathlib import Path
from config import DATA_DIR

SCRAPED_PATH = DATA_DIR / "live_scraped_reviews.parquet"


def save_scraped_reviews(reviews: list):
    if not reviews:
        print("[scraper] No scraped reviews to save.")
        return

    df_new = pd.DataFrame(reviews)

    if SCRAPED_PATH.exists():
        df_old = pd.read_parquet(SCRAPED_PATH)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all.to_parquet(SCRAPED_PATH, index=False)
    print(f"[scraper] Saved {len(df_new)} new reviews → {SCRAPED_PATH}")