# product_insights/tracker.py

"""
Product Snapshot Tracker

This module:
- Reads live_scraped_products.parquet (latest scrape)
- Appends rows to product_history.parquet
- Normalizes columns and dtypes so Parquet writing never fails
- Adds a 'category' placeholder if missing (optional)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

from config.settings import DATA_DIR

SCRAPED_PRODUCTS = DATA_DIR / "live_scraped_products.parquet"
PRODUCT_HISTORY = DATA_DIR / "product_history.parquet"


# ---------------------------------------------------------
# Safe numeric parsers
# ---------------------------------------------------------

def _safe_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        x = x.replace("$", "").replace(",", "").strip()
        if x == "":
            return None
        try:
            return float(x.split()[0])
        except:
            return None
    return None


def _safe_int(x):
    if x is None:
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        try:
            return int(x)
        except:
            return None
    if isinstance(x, str):
        x = x.replace(",", "").strip()
        if x == "":
            return None
        try:
            return int(x.split()[0])
        except:
            return None
    return None


# ---------------------------------------------------------
# Load latest snapshot
# ---------------------------------------------------------

def load_latest_snapshot() -> pd.DataFrame | None:
    if not SCRAPED_PRODUCTS.exists():
        print("[product-tracker] No scraped product file found.")
        return None

    try:
        df = pd.read_parquet(SCRAPED_PRODUCTS)
        print(f"[product-tracker] Loaded {len(df)} product rows from snapshot.")
        return df
    except Exception as e:
        print(f"[product-tracker] ERROR reading snapshot: {e}")
        return None


# ---------------------------------------------------------
# Normalize product fields
# ---------------------------------------------------------

def normalize_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee fields exist and are correctly typed."""

    desired_cols = [
        "asin",
        "title",
        "brand",
        "rating",
        "rating_count",
        "price",
        "bullets",
        "bsr",
        "timestamp",
        "category",
        "source",
    ]

    # Create missing columns
    for col in desired_cols:
        if col not in df.columns:
            df[col] = None

    # Convert rating, price → float
    df["rating"] = df["rating"].apply(_safe_float)
    df["price"] = df["price"].apply(_safe_float)

    # Convert rating_count, bsr → int
    df["rating_count"] = df["rating_count"].apply(_safe_int)
    df["bsr"] = df["bsr"].apply(_safe_int)

    # Guarantee bullets is a list
    df["bullets"] = df["bullets"].apply(lambda x: x if isinstance(x, list) else [])

    return df[desired_cols]


# ---------------------------------------------------------
# Append snapshot to history
# ---------------------------------------------------------

def append_snapshot_to_history() -> None:
    df_new = load_latest_snapshot()
    if df_new is None or df_new.empty:
        print("[product-tracker] Nothing to append.")
        return

    df_new = normalize_snapshot(df_new)

    if PRODUCT_HISTORY.exists():
        try:
            df_old = pd.read_parquet(PRODUCT_HISTORY)
        except Exception as e:
            print(f"[product-tracker] ERROR reading history file: {e}")
            df_old = pd.DataFrame()
    else:
        df_old = pd.DataFrame()

    # Align columns
    for col in df_new.columns:
        if col not in df_old.columns:
            df_old[col] = None

    for col in df_old.columns:
        if col not in df_new.columns:
            df_new[col] = None

    df_combined = pd.concat([df_old, df_new], ignore_index=True)

    try:
        df_combined.to_parquet(PRODUCT_HISTORY, index=False)
        print(
            f"[product-tracker] History updated: +{len(df_new)} rows "
            f"→ {PRODUCT_HISTORY} (total={len(df_combined)})"
        )
    except Exception as e:
        print(f"[product-tracker] ERROR writing history parquet: {e}")