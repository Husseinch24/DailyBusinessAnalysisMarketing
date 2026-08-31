# scrapers/google_trends.py

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, List

from pytrends.request import TrendReq
import pandas as pd


def fetch_google_trend(
    keyword: str,
    geo: str = "US",
    timeframe: str = "today 3-m",
) -> Dict[str, Any]:
    """
    Fetch Google Trends interest_over_time for a single keyword.

    Returns a dictionary:
    {
        "keyword": "<keyword>",
        "trend_points": [
            {"timestamp": "...", "score": 0-100},
            ...
        ]
    }

    Safe: on error returns empty trend_points.
    """

    if not keyword or not keyword.strip():
        print("[trends] Empty keyword, skipping.")
        return {"keyword": keyword, "trend_points": []}

    kw = keyword.strip()
    print(f"[trends] Fetching Google Trends for '{kw}'")

    try:
        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload([kw], cat=0, timeframe=timeframe, geo=geo, gprop="")
        df = pytrends.interest_over_time()

        if df.empty or kw not in df.columns:
            print(f"[trends] No data returned for '{kw}'")
            return {"keyword": kw, "trend_points": []}

        # Build list of records
        trend_points: List[Dict[str, Any]] = []
        for ts, row in df.iterrows():
            ts_str = ts.to_pydatetime().isoformat()
            score = int(row[kw]) if pd.notna(row[kw]) else 0
            trend_points.append({"timestamp": ts_str, "score": score})

        return {"keyword": kw, "trend_points": trend_points}

    except Exception as e:
        print(f"[trends] ERROR fetching Google Trends for '{kw}': {e}")
        return {"keyword": kw, "trend_points": []}