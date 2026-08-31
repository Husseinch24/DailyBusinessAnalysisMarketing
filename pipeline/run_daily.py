#!/usr/bin/env python3
"""
run_daily.py

Hybrid pipeline entrypoint.

Steps:

0. Web scraping (optional, driven by config)
   - Google Trends
   - Amazon product pages
   - Append product snapshot to product history

1. Ingestion
   - Build data/daily_batch.parquet

2. Analysis
   - Build data/daily_metrics.json

3. LLM summarization (Gemini) — review metrics

3.5 Product Intelligence (Gemini) — product history (if available)

4. Visualization
   - PNG plots + dashboard.html

5. Notifications
   - Email / Telegram / Slack (reads notification_config.json)

This file now supports external configuration from ui_config.json,
written by the Streamlit UI in ui/app.py.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

# Core pipeline
from ingest.daily_ingest import run_ingestion
from analysis.engine import run_analysis
from summarize.summarizer import run_summarizer
from visualize.report_viz import visualize_all
from notify.notifier import notify_all

# Scrapers
from scrapers.amazon_product import fetch_amazon_product
from scrapers.google_trends import fetch_google_trend

# Product tracking & insights
from product_insights.tracker import append_snapshot_to_history
from product_insights.analyzer import run_product_insights

# Config
from config.settings import DATA_DIR, METRICS_PATH, PROJECT_ROOT

GOOGLE_TRENDS_PARQUET = DATA_DIR / "google_trends.parquet"
LIVE_PRODUCTS_PARQUET = DATA_DIR / "live_scraped_products.parquet"
UI_CONFIG_PATH = PROJECT_ROOT / "ui_config.json"


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------

def load_metrics() -> Dict[str, Any]:
    if not METRICS_PATH.exists():
        print(f"[pipeline] Metrics JSON missing: {METRICS_PATH}")
        return {}
    try:
        return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[pipeline] ERROR reading metrics: {e}")
        return {}


def load_ui_config(path: Path | None) -> Dict[str, Any]:
    if path is None or not path.exists():
        print(f"[pipeline] No UI config found at {path or UI_CONFIG_PATH} — using defaults.")
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        print(f"[pipeline] Loaded UI config from {path}")
        return cfg
    except Exception as e:
        print(f"[pipeline] ERROR reading UI config: {e}")
        return {}


def save_google_trends(trend_dict: Dict[str, Any]) -> None:
    """Save Google Trends data into a parquet file."""
    if not trend_dict:
        print("[pipeline] Empty Google Trends dict — skipping save.")
        return

    points = trend_dict.get("trend_points", [])
    keyword = trend_dict.get("keyword", "unknown")

    if not points:
        print("[pipeline] No Google Trends points to save; skipping.")
        return

    try:
        df_new = pd.DataFrame(points)
        df_new["keyword"] = keyword
        df_new["source"] = "google_trends"

        if GOOGLE_TRENDS_PARQUET.exists():
            df_old = pd.read_parquet(GOOGLE_TRENDS_PARQUET)
            df_all = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_all = df_new

        df_all.to_parquet(GOOGLE_TRENDS_PARQUET, index=False)
        print(f"[pipeline] Saved {len(df_new)} trend points → {GOOGLE_TRENDS_PARQUET}")
    except Exception as e:
        print(f"[pipeline] ERROR saving Google Trends data: {e}")


def save_product_pages(products: List[Dict[str, Any]]) -> None:
    """Save scraped product-page data to parquet for ingestion & history."""
    if not products:
        print("[pipeline] No product pages scraped; skipping save.")
        return

    try:
        df_new = pd.DataFrame(products)

        if LIVE_PRODUCTS_PARQUET.exists():
            df_old = pd.read_parquet(LIVE_PRODUCTS_PARQUET)
            df_all = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_all = df_new

        df_all.to_parquet(LIVE_PRODUCTS_PARQUET, index=False)
        print(f"[pipeline] Saved {len(df_new)} product pages → {LIVE_PRODUCTS_PARQUET}")
    except Exception as e:
        print(f"[pipeline] ERROR saving product pages: {e}")


# ---------------------------------------------------
# Main Pipeline
# ---------------------------------------------------

def run_pipeline(days: int = 100, config: Dict[str, Any] | None = None) -> None:
    """
    Main orchestrator. `config` comes from ui_config.json, if provided.

    Config keys used:
      - ingest_days (int)
      - scrape_products (bool)
      - fetch_trends (bool)
      - asin_list (list[str])
    """
    cfg = config or {}

    # Resolve flags from config
    ingest_days = int(cfg.get("ingest_days", days))
    scrape_products = bool(cfg.get("scrape_products", True))
    fetch_trends_flag = bool(cfg.get("fetch_trends", True))
    asin_override = cfg.get("asin_list") or []

    print("=== DAILY MARKETING PIPELINE START ===")
    print(f"UTC now: {datetime.utcnow().isoformat()}Z")
    print(f"[pipeline] Config → ingest_days={ingest_days}, "
          f"scrape_products={scrape_products}, fetch_trends={fetch_trends_flag}, "
          f"asin_override_count={len(asin_override)}")

    # -----------------------------------------------------
    # 0. SCRAPING (before ingestion)
    # -----------------------------------------------------
    print("\nStep 0: Web Scraping Product Pages & Google Trends")

    # (A) Google Trends
    if fetch_trends_flag:
        try:
            print("[trends] Fetching Google Trends for 'baby monitor'")
            trend_data = fetch_google_trend("baby monitor")
            save_google_trends(trend_data)
        except Exception as e:
            print(f"[pipeline] ERROR during Google Trends scraping: {e}")
    else:
        print("[pipeline] Google Trends disabled by config.")

    # (B) Amazon Product Pages
    products_scraped: List[Dict[str, Any]] = []

    # 1) preferred: ASINs from UI config
    asin_list: List[str] = []
    if asin_override:
        asin_list = asin_override
        print(f"[pipeline] Using ASINs from UI config: {asin_list}")
    else:
        # 2) fallback: ASINs from top_selling_products in metrics
        if METRICS_PATH.exists():
            metrics = load_metrics()
            top_list = metrics.get("top_selling_products") or []
            asin_list = [p.get("asin") for p in top_list[:3] if p.get("asin")]
            print(f"[pipeline] Using ASINs from metrics: {asin_list}")
        else:
            print("[pipeline] No metrics yet; no ASINs available from metrics.")

    if scrape_products and asin_list:
        for asin in asin_list:
            try:
                products_scraped.append(fetch_amazon_product(asin))
            except Exception as e:
                print(f"[pipeline] ERROR scraping product page for ASIN {asin}: {e}")
        save_product_pages(products_scraped)
    elif scrape_products and not asin_list:
        print("[pipeline] scrape_products=True but no ASINs available → skipping product-page scrape.")
    else:
        print("[pipeline] Product-page scraping disabled by config.")

    # -----------------------------------------------------
    # 0.5 Product Tracking (optional history)
    # -----------------------------------------------------
    print("\nStep 0.5: Product Tracking (append snapshots to history)")
    try:
        append_snapshot_to_history()
    except Exception as e:
        print(f"[pipeline] ERROR in product tracking: {e}")

    # -----------------------------------------------------
    # 1. INGESTION
    # -----------------------------------------------------
    print(f"\nStep 1: Ingestion (last {ingest_days} day(s))")
    run_ingestion(days=ingest_days)

    # -----------------------------------------------------
    # 2. ANALYSIS
    # -----------------------------------------------------
    print("\nStep 2: Analysis")
    run_analysis()

    # -----------------------------------------------------
    # 3. REVIEW SUMMARY (Gemini)
    # -----------------------------------------------------
    print("\nStep 3: LLM summarization (Gemini) — Review Metrics")
    run_summarizer()

    # -----------------------------------------------------
    # 3.5 PRODUCT INTELLIGENCE (Gemini)
    # -----------------------------------------------------
    print("\nStep 3.5: Product Intelligence (Gemini) — Product History")
    try:
        run_product_insights(top_n=20)
    except Exception as e:
        print(f"[pipeline] ERROR during product insights step: {e}")

    # -----------------------------------------------------
    # 4. VISUALIZATION
    # -----------------------------------------------------
    print("\nStep 4: Visualization")
    visualize_all()

    # -----------------------------------------------------
    # 5. NOTIFICATIONS
    # -----------------------------------------------------
    print("\nStep 5: Notifications")
    notify_all()

    print("\n=== PIPELINE COMPLETE ===")


# ---------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional path to ui_config.json (from Streamlit UI)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Override ingest days (takes precedence over config file).",
    )
    args = parser.parse_args()

    cfg: Dict[str, Any] = {}
    if args.config:
        cfg = load_ui_config(Path(args.config))
    else:
        cfg = load_ui_config(UI_CONFIG_PATH)

    # Resolve ingest days precedence: CLI > config > default
    if args.days is not None:
        days = args.days
    else:
        days = int(cfg.get("ingest_days", 100))

    run_pipeline(days=days, config=cfg)


if __name__ == "__main__":
    main()