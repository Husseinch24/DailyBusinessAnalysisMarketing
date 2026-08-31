import pandas as pd
from pathlib import Path
from config.settings import DATA_DIR

TRENDS_PARQUET = DATA_DIR / "google_trends.parquet"

def save_trend_data(trend_dict):
    """
    Save Google Trends result as a Parquet dataset so ingestion can read it.
    Does NOT fail if empty.
    """

    keyword = trend_dict.get("keyword")
    points = trend_dict.get("trend_points", [])

    if not points:
        print("[trends] No trend points to save.")
        return

    df_new = pd.DataFrame(points)
    df_new["keyword"] = keyword

    if TRENDS_PARQUET.exists():
        df_old = pd.read_parquet(TRENDS_PARQUET)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all.to_parquet(TRENDS_PARQUET, index=False)
    print(f"[trends] Saved {len(df_new)} trend points → {TRENDS_PARQUET}")
