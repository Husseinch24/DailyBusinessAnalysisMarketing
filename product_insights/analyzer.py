# product_insights/analyzer.py

"""
Product Intelligence Analyzer

- Reads data/product_history.parquet
- Computes per-ASIN metrics:
    * latest price
    * latest rating
    * latest rating_count
    * delta rating_count vs previous snapshot
    * latest BSR (if available) + delta
- Saves JSON metrics
- Asks Gemini for a focused product intelligence report
- Writes Markdown + TXT reports into /reports
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

import os
import json
import pandas as pd
import google.generativeai as genai

from config.settings import DATA_DIR, REPORTS_DIR, GEMINI_MODEL

PRODUCT_HISTORY_PATH = DATA_DIR / "product_history.parquet"
PRODUCT_METRICS_JSON = DATA_DIR / "product_metrics.json"


# --------------------------------------------------------
# Helpers for safe numeric parsing
# --------------------------------------------------------

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
        except Exception:
            return None
    return None


def _safe_int(x):
    if x is None:
        return 0
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        try:
            return int(x)
        except Exception:
            return 0
    if isinstance(x, str):
        x = x.replace(",", "").strip()
        if x == "":
            return 0
        parts = x.split()
        try:
            return int(parts[0])
        except Exception:
            return 0
    return 0


# --------------------------------------------------------
# Data loading & metrics
# --------------------------------------------------------

def load_history() -> pd.DataFrame:
    if not PRODUCT_HISTORY_PATH.exists():
        print(f"[product-analyzer] No product history at {PRODUCT_HISTORY_PATH}")
        return pd.DataFrame()
    try:
        df = pd.read_parquet(PRODUCT_HISTORY_PATH)
        print(f"[product-analyzer] Loaded {len(df)} rows from product history.")
        return df
    except Exception as e:
        print(f"[product-analyzer] ERROR reading product history: {e}")
        return pd.DataFrame()


def compute_product_metrics(
    df: pd.DataFrame, top_n: int | None = None
) -> Dict[str, Any]:
    if df.empty:
        return {"products": [], "generated_at": datetime.utcnow().isoformat() + "Z"}

    # Normalize timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.Timestamp.utcnow()

    df = df.sort_values(["asin", "timestamp"])

    products_out: List[Dict[str, Any]] = []

    for asin, g in df.groupby("asin"):
        g = g.sort_values("timestamp")

        latest = g.iloc[-1]
        prev = g.iloc[-2] if len(g) >= 2 else None

        def _safe(col, row):
            return row[col] if (row is not None and col in row.index) else None

        latest_price_raw = _safe("price", latest)
        prev_price_raw = _safe("price", prev)

        latest_rating_raw = _safe("rating", latest)
        prev_rating_raw = _safe("rating", prev)

        latest_count_raw = _safe("rating_count", latest)
        prev_count_raw = _safe("rating_count", prev)

        latest_bsr_raw = _safe("bsr", latest)
        prev_bsr_raw = _safe("bsr", prev)

        latest_price = _safe_float(latest_price_raw)
        prev_price = _safe_float(prev_price_raw)
        latest_rating = _safe_float(latest_rating_raw)
        prev_rating = _safe_float(prev_rating_raw)
        latest_count = _safe_int(latest_count_raw)
        prev_count = _safe_int(prev_count_raw)

        latest_bsr = _safe_int(latest_bsr_raw) if latest_bsr_raw is not None else None
        prev_bsr = _safe_int(prev_bsr_raw) if prev_bsr_raw is not None else None

        products_out.append(
            {
                "asin": asin,
                "title": _safe("title", latest),
                "brand": _safe("brand", latest),
                "category": _safe("category", latest),
                "latest_price": latest_price,
                "prev_price": prev_price,
                "latest_rating": latest_rating,
                "prev_rating": prev_rating,
                "latest_rating_count": latest_count,
                "prev_rating_count": prev_count,
                "delta_rating_count": latest_count - prev_count,
                "latest_bsr": latest_bsr,
                "prev_bsr": prev_bsr,
                "delta_bsr": (
                    (prev_bsr - latest_bsr)
                    if (latest_bsr is not None and prev_bsr is not None)
                    else None
                ),
                "last_seen": latest["timestamp"].isoformat()
                if isinstance(latest["timestamp"], pd.Timestamp)
                else str(latest.get("timestamp")),
            }
        )

    # Sort by momentum (rating_count delta)
    products_out.sort(key=lambda x: x.get("delta_rating_count", 0), reverse=True)

    if top_n is not None and top_n > 0:
        products_out = products_out[:top_n]

    payload: Dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "products": products_out,
    }

    PRODUCT_METRICS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[product-analyzer] Metrics JSON saved → {PRODUCT_METRICS_JSON}")

    return payload


# --------------------------------------------------------
# Gemini Integration
# --------------------------------------------------------

def configure_gemini() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Environment variable GEMINI_API_KEY is not set.")
    genai.configure(api_key=api_key)


def build_prompt(metrics_payload: Dict[str, Any]) -> str:
    products = metrics_payload.get("products", [])

    lines: List[str] = []

    lines.append(
        "You are a senior ecommerce product strategist. "
        "You will see product tracking data from Amazon (ASIN-level snapshots). "
        "Focus on performance, risk, and opportunities.\n"
    )

    lines.append("=== PRODUCT METRICS (TRIMMED) ===")
    lines.append(json.dumps(products, indent=2))

    lines.append(
        """
Write a concise **Product Intelligence Report** with:

1. Executive Summary (3–6 bullets)
2. Products with positive momentum (rating_count growth, improving BSR)
3. Products showing risk (stagnant or declining rating_count, worse BSR, low rating)
4. Price & positioning observations (if price present)
5. Recommended actions (5–10 bullets) such as:
   - campaigns to ramp / pause
   - product page improvements (title, images, price anchors)
   - review generation and social proof
   - inventory or portfolio moves (e.g., promote brand X vs Y)

Keep it direct, actionable, and business-focused. Assume the reader is a busy head of growth.
"""
    )

    return "\n".join(lines)


def generate_product_report(prompt: str) -> str:
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text if hasattr(response, "text") else str(response)


def save_product_reports(report_text: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    md_path = REPORTS_DIR / f"product_intel_{date_str}.md"
    txt_path = REPORTS_DIR / "product_intel.txt"

    md_path.write_text(
        f"# Product Intelligence Report\n\n"
        f"_Generated at: {datetime.utcnow().isoformat()}Z_\n\n"
        f"{report_text}",
        encoding="utf-8",
    )
    txt_path.write_text(report_text, encoding="utf-8")

    print(f"[product-analyzer] Markdown report: {md_path}")
    print(f"[product-analyzer] TXT report:      {txt_path}")


def run_product_insights(top_n: int = 20) -> None:
    """Main entry point used from the daily pipeline."""
    df_hist = load_history()
    if df_hist.empty:
        print("[product-analyzer] No history → skipping product insights.")
        return

    payload = compute_product_metrics(df_hist, top_n=top_n)

    if not payload.get("products"):
        print("[product-analyzer] No products in metrics → skipping Gemini.")
        return

    try:
        print("[product-analyzer] Configuring Gemini…")
        configure_gemini()
        prompt = build_prompt(payload)
        print("[product-analyzer] Generating Product Intelligence report with Gemini…")
        report_text = generate_product_report(prompt)
        save_product_reports(report_text)
    except Exception as e:
        print(f"[product-analyzer] ERROR during Gemini product insights: {e}")


if __name__ == "__main__":
    run_product_insights()