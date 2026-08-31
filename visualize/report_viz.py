#!/usr/bin/env python3

"""
VADER-Optimized Marketing Dashboard
----------------------------------
Generates:
- PNG plots (sentiment distribution, polarity split, top sellers, etc.)
- Interactive Plotly dashboard (HTML)
"""

import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Updated import for the new package layout
from config.settings import METRICS_PATH, DAILY_BATCH_PATH, REPORTS_DIR

# Optional libs
try:
    import seaborn as sns
except ImportError:
    sns = None

try:
    from wordcloud import WordCloud
except ImportError:
    WordCloud = None

try:
    import plotly.express as px
except ImportError:
    px = None

PLOTS_DIR = REPORTS_DIR / "plots"


# ===========================================================
# Helpers
# ===========================================================

def _ensure_plots_dir():
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_metrics():
    if not METRICS_PATH.exists():
        raise FileNotFoundError(f"[viz] Metrics file missing: {METRICS_PATH}")
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


def _load_daily_reviews():
    if DAILY_BATCH_PATH.exists():
        return pd.read_parquet(DAILY_BATCH_PATH)
    print("[viz] daily_batch.parquet missing — dashboard may be limited.")
    return pd.DataFrame()


def _normalize_sentiment_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "sentiment_score" in df:
        return df

    if "avg_sentiment" in df:
        df = df.rename(columns={"avg_sentiment": "sentiment_score"})
        return df

    if "avg_sentiment_ai" in df:
        df = df.rename(columns={"avg_sentiment_ai": "sentiment_score"})
        return df

    df["sentiment_score"] = 0.0
    return df


def _debug_sentiment(payload):
    lst = payload.get("sentiment_per_product", [])
    print("\n=== DEBUG: SENTIMENT_PER_PRODUCT ===")
    print("Type:", type(lst))
    print("Count:", len(lst))

    if not lst:
        print("EMPTY\n")
        return

    df = pd.DataFrame(lst)
    print("\nFIRST 10 ROWS:\n", df.head(10))
    print("\nCOLUMNS:", df.columns.tolist())
    print("\nSUMMARY:\n", df.describe(include="all"))
    print("====================================\n")


# ===========================================================
# PNG PLOTS
# ===========================================================

def plot_sentiment_distribution(payload):
    lst = payload.get("sentiment_per_product", [])
    if not lst:
        print("[viz] No sentiment data.")
        return

    scores = []
    for x in lst:
        if "sentiment_score" in x:
            scores.append(x["sentiment_score"])
        elif "avg_sentiment" in x:
            scores.append(x["avg_sentiment"])
        else:
            scores.append(0.0)

    _ensure_plots_dir()
    out = PLOTS_DIR / "sentiment_distribution.png"

    plt.figure(figsize=(8, 4))
    if sns:
        sns.histplot(scores, bins=25, kde=True)
    else:
        plt.hist(scores, bins=25)

    plt.title("Sentiment Distribution (VADER)")
    plt.xlabel("Sentiment Score")
    plt.tight_layout()
    plt.savefig(out, dpi=180)
    plt.close()
    print(f"[viz] Saved → {out}")


def plot_vader_polarity(payload):
    lst = payload.get("sentiment_per_product", [])
    if not lst:
        print("[viz] No sentiment.")
        return

    scores = []
    for x in lst:
        if "sentiment_score" in x:
            scores.append(x["sentiment_score"])
        elif "avg_sentiment" in x:
            scores.append(x["avg_sentiment"])
        else:
            scores.append(0)

    pos = sum(s > 0.05 for s in scores)
    neg = sum(s < -0.05 for s in scores)
    neu = len(scores) - pos - neg

    df_plot = pd.DataFrame({"Polarity": ["Positive", "Neutral", "Negative"],
                            "Count": [pos, neu, neg]})

    _ensure_plots_dir()
    out = PLOTS_DIR / "vader_polarity_split.png"

    plt.figure(figsize=(6, 4))
    plt.bar(df_plot["Polarity"], df_plot["Count"],
            color=["#4caf50", "#9e9e9e", "#e53935"])
    plt.title("VADER Polarity Split (Products)")
    plt.tight_layout()
    plt.savefig(out, dpi=180)
    plt.close()
    print(f"[viz] Saved → {out}")


def plot_top_selling(payload):
    ts = payload.get("top_selling_products", [])
    if not ts:
        print("[viz] No top sellers.")
        return

    ts = ts[:10]

    _ensure_plots_dir()
    out = PLOTS_DIR / "top_selling_products.png"

    plt.figure(figsize=(10, 4))
    plt.bar([x["asin"] for x in ts], [x["sales_score"] for x in ts])
    plt.xticks(rotation=45, ha="right")
    plt.title("Top Estimated Sellers")
    plt.tight_layout()
    plt.savefig(out, dpi=180)
    plt.close()
    print(f"[viz] Saved → {out}")


def plot_campaign_risks(payload):
    risks = payload.get("campaign_risk_products", [])
    if not risks:
        print("[viz] No risk products.")
        return

    risks = risks[:10]

    _ensure_plots_dir()
    out = PLOTS_DIR / "campaign_risk_products.png"

    plt.figure(figsize=(10, 4))
    plt.bar([x["asin"] for x in risks],
            [x["avg_rating"] for x in risks],
            color="red")
    plt.xticks(rotation=45, ha="right")
    plt.title("Campaign Risk Products")
    plt.tight_layout()
    plt.savefig(out, dpi=180)
    plt.close()
    print(f"[viz] Saved → {out}")


def plot_rating_distribution_top(df, payload):
    if df.empty:
        return

    ts = payload.get("top_selling_products", [])
    if not ts:
        return

    top = [x["asin"] for x in ts[:5]]
    sub = df[df["asin"].isin(top)]

    if sub.empty:
        return

    _ensure_plots_dir()
    out = PLOTS_DIR / "rating_distribution_top_products.png"

    sub["rating_num"] = pd.to_numeric(sub["rating"], errors="coerce")

    plt.figure(figsize=(9, 5))
    if sns:
        sns.boxplot(data=sub, x="asin", y="rating_num")
    else:
        plt.scatter(sub["asin"], sub["rating_num"])
    plt.title("Rating Distribution for Top Sellers")
    plt.tight_layout()
    plt.savefig(out, dpi=180)
    plt.close()
    print(f"[viz] Saved → {out}")



# ===========================================================
# Wordcloud
# ===========================================================

def plot_complaint_wordcloud(payload):
    if WordCloud is None:
        return

    words = payload.get("complaint_keywords", {}).get("global", [])
    if not words:
        return

    freqs = {w["word"]: w["count"] for w in words}

    _ensure_plots_dir()
    out = PLOTS_DIR / "complaints_wordcloud.png"

    wc = WordCloud(width=900, height=400, background_color="white")
    wc.generate_from_frequencies(freqs)
    wc.to_file(str(out))
    print(f"[viz] Saved → {out}")


# ===========================================================
# Review Highlights (HTML)
# ===========================================================

def extract_review_panels(df: pd.DataFrame, n=3):
    if df.empty:
        return "<p>No reviews available.</p>"

    df["rating_num"] = pd.to_numeric(df["rating"], errors="coerce")

    best = df.sort_values("rating_num", ascending=False).head(n)
    worst = df.sort_values("rating_num", ascending=True).head(n)

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def build(title, rows):
        html = f"<h3>{title}</h3><ul class='review-list'>"
        for _, r in rows.iterrows():
            snippet = esc(r.get("text", "")[:260])
            html += f"<li><b>{r['asin']}</b> · Rating {r['rating_num']}<br>{snippet}</li>"
        html += "</ul>"
        return html

    return build("⭐ Best Reviews", best) + build("⚠ Worst Reviews", worst)

# ===========================================================
# Dashboard Builder
# ===========================================================

def build_interactive_dashboard(payload, df):
    if px is None:
        print("[viz] Plotly missing — skipping dashboard.")
        return

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "dashboard.html"

    sentiment_df = _normalize_sentiment_df(
        pd.DataFrame(payload.get("sentiment_per_product", []))
    )

    risks_df = pd.DataFrame(payload.get("campaign_risk_products", []))
    top_df = pd.DataFrame(payload.get("top_selling_products", []))

    metrics = payload.get("metrics", {})
    avg_sent = float(sentiment_df["sentiment_score"].mean()) if not sentiment_df.empty else 0.0
    review_panels = extract_review_panels(df)

    # ======== BEGIN HTML ========
    html = """
    <html>
    <head>
    <meta charset="utf-8" />
    <title>Marketing Insight Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
      body { font-family: 'Segoe UI'; background:#f4f5f7; padding:30px; }
      h1 { text-align:center; }
      .layout { max-width:1280px; margin:auto; }
      .kpis { display:flex; gap:12px; flex-wrap:wrap; justify-content:center; }
      .kpi {
         background:white; padding:14px; border-radius:10px;
         box-shadow:0 3px 8px rgba(0,0,0,0.08);
         min-width:180px; text-align:center;
      }
      .chart {
         background:white; padding:20px; border-radius:12px;
         margin:24px 0; box-shadow:0 3px 10px rgba(0,0,0,0.08);
      }
      .plotly-graph-div {
    width: 100% !important;
    height: 520px !important;
}
    </style>
    </head>
    <body>
    <div class="layout">
      <h1>Daily Marketing Insight Dashboard</h1>

      <div class="kpis">
    """

    # KPIs
    kpi_vals = {
        "Total Reviews": metrics.get("rows", 0),
        "Unique Products": metrics.get("unique_asins", 0),
        "Avg Rating": round(metrics.get("overall_avg_rating", 0), 2),
        "Avg Sentiment": round(avg_sent, 3),
        "Verified %": f"{metrics.get('overall_verified_ratio', 0)*100:.1f}%",
        "Positive %": f"{metrics.get('overall_positive_ratio', 0)*100:.1f}%",
    }

    for k, v in kpi_vals.items():
        html += f"<div class='kpi'><b>{k}</b><br><span>{v}</span></div>"

    html += "</div>"

    # ========== Top Sellers ==========
    if not top_df.empty:
        df_top = top_df.head(20).copy()
        df_top["asin_short"] = df_top["asin"].str.slice(0, 6) + "…"
        fig_top = px.bar(
            df_top,
            x="asin_short",
            y="sales_score",
            hover_data=["asin"],
            title="Top Selling Products"
        )
        html += f"<div class='chart'>{fig_top.to_html(full_html=False, include_plotlyjs=False)}</div>"

    # ========== Campaign Risk ==========
    if not risks_df.empty:
        df_risk = risks_df.head(20).copy()
        df_risk["asin_short"] = df_risk["asin"].str.slice(0, 6) + "…"
        fig_risk = px.bar(
            df_risk,
            x="asin_short",
            y="avg_rating",
            color="avg_rating",
            color_continuous_scale="Reds",
            hover_data=["asin"],
            title="Campaign Risk Products"
        )
        html += f"<div class='chart'>{fig_risk.to_html(full_html=False, include_plotlyjs=False)}</div>"

    # ========== Review Highlights ==========
    html += f"""
    <div class="chart">
      <h2>Review Highlights</h2>
      {review_panels}
    </div>
    """

    # ========== JS Toggle ==========
    html += """
    </div>
    <script>
      document.addEventListener("DOMContentLoaded", () => {
        const sel = document.getElementById("scatter-category");
        const allDiv = document.getElementById("scatter-all");
        const babyDiv = document.getElementById("scatter-baby");
        const gamesDiv = document.getElementById("scatter-games");

        sel.addEventListener("change", () => {
          allDiv.style.display = sel.value === "all" ? "" : "none";
          babyDiv.style.display = sel.value === "baby" ? "" : "none";
          gamesDiv.style.display = sel.value === "games" ? "" : "none";
        });
      });
    </script>
    </body></html>
    """

    out.write_text(html, encoding="utf-8")
    print(f"[viz] Dashboard saved → {out}")


# ===========================================================
# Main
# ===========================================================

def visualize_all():
    print("[viz] Loading data...")
    payload = _load_metrics()
    df = _load_daily_reviews()

    _debug_sentiment(payload)

    print("[viz] Generating PNG plots...")
    plot_sentiment_distribution(payload)
    plot_vader_polarity(payload)
    plot_top_selling(payload)
    plot_campaign_risks(payload)
    plot_rating_distribution_top(df, payload)
    plot_complaint_wordcloud(payload)

    print("[viz] Building dashboard...")
    build_interactive_dashboard(payload, df)

    print("[viz] Done.")


if __name__ == "__main__":
    visualize_all()
