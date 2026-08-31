#!/usr/bin/env python3
"""
Ingestion pipeline for MarketingProject (FINAL VERSION)

What this DOES:
- Load raw review Parquet files from /data
- Optionally load live_scraped_reviews.parquet (if exists)
- Normalize timestamps
- Filter last N days (dataset-based)
- Deduplicate
- Compute VADER sentiment (or fill missing)
- Save data/daily_batch.parquet

What this DOES NOT DO:
- It DOES NOT load or merge Google Trends (different schema)
- It DOES NOT merge product-page snapshots (used only by product_history)
"""

import argparse
from datetime import timedelta
from pathlib import Path

import polars as pl
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config.settings import DATA_DIR, DAILY_BATCH_PATH, TIMESTAMP_COL

analyzer = SentimentIntensityAnalyzer()

SCRAPED_REVIEWS_PATH = DATA_DIR / "live_scraped_reviews.parquet"


# ============================================================
# LOAD RAW PARQUET FILES
# ============================================================

def load_all_parquet_files(input_dir: Path) -> pl.DataFrame:
    print(f"[load] Scanning directory: {input_dir}")

    # Exclude derived / auxiliary files
    excluded = {
        DAILY_BATCH_PATH.name,
        SCRAPED_REVIEWS_PATH.name,
        "google_trends.parquet",
        "live_scraped_products.parquet",
        "product_history.parquet",
        "product_metrics.json",
        "ui_config.json",
    }

    files = [f for f in input_dir.glob("*.parquet") if f.name not in excluded]

    print(f"[load] Found {len(files)} raw parquet files")

    if not files:
        return pl.DataFrame()

    dfs = []
    for f in files:
        print(f"[read] {f.name}")
        try:
            df = pl.read_parquet(f)
            df = df.with_columns(pl.lit(f.name).alias("__source_file"))
            dfs.append(df)
        except Exception as e:
            print(f"[error] Could not load {f}: {e}")

    if not dfs:
        print("[load] ERROR: No valid files loaded.")
        return pl.DataFrame()

    combined = pl.concat(dfs, how="vertical_relaxed")
    print(f"[load] Combined rows: {combined.height:,}")

    return combined


# ============================================================
# LOAD SCRAPED REVIEWS (OPTIONAL)
# ============================================================

def load_scraped_reviews() -> pl.DataFrame | None:
    if not SCRAPED_REVIEWS_PATH.exists():
        print("[scrape] No scraped reviews file found.")
        return None

    try:
        df = pl.read_parquet(SCRAPED_REVIEWS_PATH)
        print(f"[scrape] Loaded {df.height:,} scraped review rows")
        return df
    except Exception as e:
        print(f"[scrape] ERROR reading scraped reviews: {e}")
        return None


# ============================================================
# SENTIMENT ANALYSIS
# ============================================================

def compute_sentiment(df: pl.DataFrame) -> pl.DataFrame:
    """
    Fill sentiment_score using VADER.
    If sentiment_score already exists, only fill nulls.
    """
    if "text" not in df.columns:
        print("[sentiment] No 'text' column → skipping VADER fill.")
        return df

    if "sentiment_score" not in df.columns:
        df = df.with_columns(
            pl.lit(None).cast(pl.Float64).alias("sentiment_score")
        )

    def score(txt):
        if txt is None or not isinstance(txt, str):
            return 0.0
        return analyzer.polarity_scores(txt)["compound"]

    print("[sentiment] Filling missing sentiment_score with VADER…")

    df = df.with_columns(
        pl.when(pl.col("sentiment_score").is_null())
        .then(pl.col("text").map_elements(score, return_dtype=pl.Float64))
        .otherwise(pl.col("sentiment_score"))
        .alias("sentiment_score")
    )

    return df


# ============================================================
# TIMESTAMP NORMALIZATION
# ============================================================

def normalize_timestamps(df: pl.DataFrame) -> pl.DataFrame:
    if TIMESTAMP_COL not in df.columns:
        print("[time] No timestamp column found.")
        return df

    print("[time] Normalizing timestamps (safe mode)...")

    import datetime
    import dateutil.parser

    def parse_any(x):
        if x is None:
            return None
        if isinstance(x, (int, float)):
            try:
                return datetime.datetime.utcfromtimestamp(x / 1000) if x > 1e12 else datetime.datetime.utcfromtimestamp(x)
            except Exception:
                return None
        if isinstance(x, str):
            try:
                return dateutil.parser.parse(x)
            except Exception:
                return None
        return None

    parsed = [parse_any(v) for v in df[TIMESTAMP_COL].to_list()]
    df = df.drop(TIMESTAMP_COL)
    df = df.with_columns(pl.Series(TIMESTAMP_COL, parsed, dtype=pl.Datetime))

    return df


# ============================================================
# FILTER LAST N DAYS
# ============================================================

def filter_last_n_days(df: pl.DataFrame, days: int) -> pl.DataFrame:
    if df.is_empty() or TIMESTAMP_COL not in df.columns:
        return df

    max_ts = df[TIMESTAMP_COL].max()
    cutoff = max_ts - timedelta(days=days)

    print(f"[filter] Max timestamp: {max_ts}")
    print(f"[filter] Cutoff:        {cutoff}")

    return df.filter(pl.col(TIMESTAMP_COL) >= cutoff)


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate(df: pl.DataFrame) -> pl.DataFrame:
    keys = [c for c in ("asin", "user_id", TIMESTAMP_COL) if c in df.columns]

    if not keys:
        print("[dedup] No valid dedup keys.")
        return df

    before = df.height
    df = df.unique(subset=keys)
    removed = before - df.height
    print(f"[dedup] Removed {removed:,} duplicates")
    return df


# ============================================================
# MAIN
# ============================================================

def run_ingestion(days: int = 365, input_dir=DATA_DIR, output=DAILY_BATCH_PATH):

    print("\n=== INGESTION START ===")

    df = load_all_parquet_files(Path(input_dir))

    scraped = load_scraped_reviews()
    if scraped is not None and not scraped.is_empty():
        print("[ingest] Merging scraped reviews…")
        df = pl.concat([df, scraped], how="vertical_relaxed")

    if df.is_empty():
        print("[warn] No data → skipping ingestion.")
        return

    df = normalize_timestamps(df)
    df = filter_last_n_days(df, days)
    df = deduplicate(df)
    df = compute_sentiment(df)

    keep = [
        "asin", "parent_asin", "rating", "title", "text",
        "sentiment_score", "images", "user_id",
        TIMESTAMP_COL, "helpful_vote", "verified_purchase", "__source_file",
    ]
    keep = [c for c in keep if c in df.columns]
    df = df.select(keep)

    output.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(output)

    print("\n=== INGESTION COMPLETE ===")
    print(f"Rows: {df.height:,}")
    if "asin" in df.columns:
        print(f"ASINs: {df['asin'].n_unique():,}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    args = p.parse_args()
    run_ingestion(days=args.days)