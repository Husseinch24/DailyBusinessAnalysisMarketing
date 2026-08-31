#!/usr/bin/env python3
"""
Analysis engine for the MarketingProject — VADER Edition (FAST & SAFE)

IMPORTANT:
- Uses ONLY the filtered + cleaned + deduped + VADER-scored dataset
  produced by Step 1 (daily_batch.parquet)
- This ensures Step 2 processes ~700k rows, not 11 million.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import re
from collections import Counter
from typing import Dict, Any, List

import pandas as pd
import numpy as np
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# UPDATED IMPORT
from config.settings import DAILY_BATCH_PATH, METRICS_PATH

analyzer = SentimentIntensityAnalyzer()


# ───────────────────────────────────────────────────────────────
# LOAD DATASETS (ONLY DAILY BATCH — FIXED)
# ───────────────────────────────────────────────────────────────

def load_daily_batch(path: Path = DAILY_BATCH_PATH) -> pd.DataFrame:
    if not path.exists():
        print(f"[warn] daily batch missing: {path}")
        return pd.DataFrame()
    return pd.read_parquet(path)


# ───────────────────────────────────────────────────────────────
# CLEANUP
# ───────────────────────────────────────────────────────────────

def _ensure_common_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["category"] = (
        df.get("__source_file", "unknown")
          .astype(str)
          .replace(".parquet", "", regex=False)
    )
    df["rating_num"] = pd.to_numeric(df.get("rating"), errors="coerce")
    df["helpful_vote_num"] = pd.to_numeric(df.get("helpful_vote"), errors="coerce").fillna(0)
    df["verified_bool"] = df.get("verified_purchase", False).astype(bool)
    df["text"] = df.get("text", "").astype(str)

    return df


# ───────────────────────────────────────────────────────────────
# VADER SENTIMENT
# ───────────────────────────────────────────────────────────────

def compute_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure df already contains VADER sentiment (ingestion computed it)."""
    if "sentiment_score" not in df:
        print("[warn] sentiment_score missing; recomputing (slow)…")

        def score(text):
            if not isinstance(text, str):
                return 0.0
            return analyzer.polarity_scores(text)["compound"]

        df["sentiment_score"] = df["text"].apply(score)

    return df


def compute_sentiment_per_product(df: pd.DataFrame):
    grouped = df.groupby("asin").agg(
        avg_rating=("rating_num", "mean"),
        review_count=("asin", "count"),
        avg_sentiment=("sentiment_score", "mean"),
        avg_helpful=("helpful_vote_num", "mean"),
        verified_ratio=("verified_bool", "mean"),
        category=("category", "first"),
    )
    return grouped.reset_index().to_dict(orient="records")


# ───────────────────────────────────────────────────────────────
# TOP SELLERS
# ───────────────────────────────────────────────────────────────

def compute_top_selling(df: pd.DataFrame, min_reviews=20):
    grouped = df.groupby("asin").agg(
        review_count=("asin", "count"),
        avg_rating=("rating_num", "mean"),
        avg_sentiment=("sentiment_score", "mean"),
        verified_ratio=("verified_bool", "mean"),
        avg_helpful=("helpful_vote_num", "mean"),
    )

    grouped = grouped[grouped["review_count"] >= min_reviews]
    if grouped.empty:
        return []

    grouped["sales_score"] = (
        grouped["review_count"]
        * grouped["verified_ratio"].clip(lower=0.05)
        * (grouped["avg_rating"].clip(lower=1.0) ** 1.2)
        * (grouped["avg_sentiment"] + 1.2)
    )

    top = grouped.sort_values("sales_score", ascending=False).head(20)
    return top.reset_index().to_dict(orient="records")


# ───────────────────────────────────────────────────────────────
# CAMPAIGN RISKS
# ───────────────────────────────────────────────────────────────

def detect_campaign_risks(df: pd.DataFrame, min_reviews=10):
    grouped = df.groupby("asin").agg(
        review_count=("asin", "count"),
        avg_rating=("rating_num", "mean"),
        avg_sentiment=("sentiment_score", "mean"),
        verified_ratio=("verified_bool", "mean"),
    )

    grouped = grouped[grouped["review_count"] >= min_reviews]

    mask = (
        (grouped["avg_rating"] < 3.5) |
        (grouped["avg_sentiment"] < 0) |
        (grouped["verified_ratio"] < 0.4)
    )

    return grouped[mask].reset_index().to_dict(orient="records")


# ───────────────────────────────────────────────────────────────
# COMPLAINT KEYWORDS
# ───────────────────────────────────────────────────────────────

STOPWORDS = set("""
the a an and or of to in for on is it this that was were but very too
""".split())

def _tokenize(text: str):
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def compute_complaint_keywords(df: pd.DataFrame, threshold=3.0):
    neg = df[df["rating_num"] <= threshold]
    counter = Counter()
    for t in neg["text"]:
        counter.update(_tokenize(t))
    return {"global": [{"word": w, "count": c} for w, c in counter.most_common(40)]}


# ───────────────────────────────────────────────────────────────
# METRICS
# ───────────────────────────────────────────────────────────────

def compute_basic_metrics(df: pd.DataFrame):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(df)),
        "unique_asins": int(df["asin"].nunique()),
        "overall_avg_rating": float(df["rating_num"].mean()),
        "overall_avg_sentiment": float(df["sentiment_score"].mean()),
        "overall_verified_ratio": float(df["verified_bool"].mean()),
        "overall_positive_ratio": float((df["sentiment_score"] > 0).mean()),
    }


# ───────────────────────────────────────────────────────────────
# REVIEW SAMPLES
# ───────────────────────────────────────────────────────────────

def sample_reviews(df: pd.DataFrame, max_per_category=40):
    out = {}
    if df.empty:
        return out

    for cat, g in df.groupby("category"):
        g = g.sort_values("helpful_vote_num", ascending=False)
        out[cat] = g.head(max_per_category).to_dict(orient="records")

    return out


# ───────────────────────────────────────────────────────────────
# SAVE OUTPUT
# ───────────────────────────────────────────────────────────────

def _to_jsonable(obj):
    """Convert NumPy & pandas types to JSON-safe forms."""
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray, list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def save_metrics(payload):
    safe = _to_jsonable(payload)
    METRICS_PATH.write_text(json.dumps(safe, indent=2), encoding="utf-8")
    print(f"[info] Saved metrics → {METRICS_PATH}")


# ───────────────────────────────────────────────────────────────
# MAIN
# ───────────────────────────────────────────────────────────────

def run_analysis():
    print("[info] Loading DAILY dataset (from ingestion)…")
    df = load_daily_batch()
    df = _ensure_common_columns(df)
    df = compute_sentiment(df)

    print(f"[info] Analyzing {len(df):,} rows")

    payload = {
        "metrics": compute_basic_metrics(df),
        "sentiment_per_product": compute_sentiment_per_product(df),
        "top_selling_products": compute_top_selling(df),
        "campaign_risk_products": detect_campaign_risks(df),
        "complaint_keywords": compute_complaint_keywords(df),
        "review_samples": sample_reviews(df),
    }

    save_metrics(payload)


if __name__ == "__main__":
    run_analysis()