# summarizer.py
"""
Summarizer for 

Reads data/daily_metrics.json produced by analysis_engine.py
and uses a Gemini model to generate a daily business summary.

Outputs:
- reports/daily_business_summary_YYYY-MM-DD.md
- reports/daily_summary.txt  (overwritten each run)
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

import google.generativeai as genai

# UPDATED IMPORTS for new structure
from config.settings import METRICS_PATH, REPORTS_DIR, GEMINI_MODEL


# ============================================================
#                  SAFE PAYLOAD TRIMMING
# ============================================================

MAX_TOP_PRODUCTS = 20
MAX_RISK_PRODUCTS = 20
MAX_SENTIMENT_ITEMS = 15
MAX_KEYWORDS = 50
MAX_RULE_RECS = 40
MAX_REVIEWS_PER_CATEGORY = 20


def safe_trim_list(data, limit):
    if not isinstance(data, list):
        return []
    return data[:limit]


def safe_trim_dict_of_lists(d: Dict[str, List], limit: int):
    out = {}
    for k, lst in d.items():
        if isinstance(lst, list):
            out[k] = lst[:limit]
    return out


def safe_summarize_dict(d: Dict, limit: int = 50):
    """
    If complaint keywords or nested dicts are massive,
    shrink keys + their lists.
    """
    out = {}
    for k, v in d.items():
        if isinstance(v, list):
            out[k] = v[:limit]
        elif isinstance(v, dict):
            out[k] = safe_trim_dict_of_lists(v, limit)
        else:
            out[k] = v
    return out


# ============================================================
#                  DATA LOADING
# ============================================================

def load_metrics(path: Path = METRICS_PATH) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"[error] Metrics file not found at {path}")
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload


# ============================================================
#               SENTIMENT BEST/WORST SPLIT
# ============================================================

def _split_best_worst(sentiment_list: List[Dict[str, Any]], top_n: int = 10):
    if not sentiment_list:
        return [], []

    sorted_by = sorted(sentiment_list, key=lambda x: x.get("sentiment_score", 0.0))
    worst = sorted_by[:top_n]
    best = list(reversed(sorted_by[-top_n:]))
    return best, worst


# ============================================================
#               PROMPT CONSTRUCTION (TOKEN SAFE)
# ============================================================

def build_prompt(payload: Dict[str, Any]) -> str:

    metrics = payload.get("metrics", {})

    sentiment_per_product = safe_trim_list(
        payload.get("sentiment_per_product", []),
        MAX_SENTIMENT_ITEMS
    )

    top_selling = safe_trim_list(
        payload.get("top_selling_products", []),
        MAX_TOP_PRODUCTS
    )

    campaign_risks = safe_trim_list(
        payload.get("campaign_risk_products", []),
        MAX_RISK_PRODUCTS
    )

    complaint_keywords = safe_summarize_dict(
        payload.get("complaint_keywords", {}),
        MAX_KEYWORDS
    )

    recommendations = safe_trim_list(
        payload.get("recommendations", []),
        MAX_RULE_RECS
    )

    raw_review_samples = payload.get("review_samples", {})
    review_samples = {}
    for cat, reviews in raw_review_samples.items():
        review_samples[cat] = reviews[:MAX_REVIEWS_PER_CATEGORY]

    best_products, worst_products = _split_best_worst(
        sentiment_per_product, top_n=10
    )

    lines = []

    lines.append(
        "You are a senior marketing and product strategy analyst for an e-commerce business.\n"
        "You will receive condensed metrics and signals about Amazon product performance.\n"
        "Your job is to create a short, high-value business report."
    )

    lines.append("\n=== HIGH-LEVEL METRICS ===")
    lines.append(json.dumps(metrics, indent=2))

    lines.append("\n=== TOP-SELLING PRODUCTS (TRIMMED) ===")
    lines.append(json.dumps(top_selling, indent=2))

    lines.append("\n=== CAMPAIGN RISK PRODUCTS (TRIMMED) ===")
    lines.append(json.dumps(campaign_risks, indent=2))

    lines.append("\n=== SENTIMENT BEST PRODUCTS ===")
    lines.append(json.dumps(best_products, indent=2))

    lines.append("\n=== SENTIMENT WORST PRODUCTS ===")
    lines.append(json.dumps(worst_products, indent=2))

    lines.append("\n=== KEY COMPLAINT THEMES (GLOBAL & CATEGORY) ===")
    lines.append(json.dumps(complaint_keywords, indent=2))

    lines.append("\n=== RULE-BASED RECOMMENDATIONS (TRIMMED) ===")
    lines.append(json.dumps(recommendations, indent=2))

    lines.append("\n=== REVIEW SAMPLES (LIGHTWEIGHT) ===")
    for category, reviews in review_samples.items():
        lines.append(f"\n--- Category: {category} ---")
        for r in reviews:
            lines.append(
                f"ASIN {r['asin']} | rating={r['rating']} | helpful={r['helpful_vote']} | verified={r['verified_purchase']}\n"
                f"Title: {r['title']}\n"
                f"Text: {r['text']}\n"
            )

    lines.append(
        """
Write a clear daily business report with:

1. Executive Summary (3–6 bullets)
2. Top Products & Growth Opportunities
3. Products Needing Campaign Changes
4. Customer Feedback & Complaint Themes
5. Recommended Action Plan (5–10 numbered steps)

Keep the report concise and business-focused.
"""
    )

    return "\n".join(lines)


# ============================================================
#               GEMINI CLIENT + SAFE RETRY
# ============================================================

def configure_gemini() -> None:
    """
    Loads Gemini API key from environment variable first.
    If not found, fallbacks to reading from:
       PROJECT_ROOT/secrets/gemini_api_key.txt
    """
    import os
    from pathlib import Path
    from config.settings import PROJECT_ROOT

    api_key = os.getenv("GEMINI_API_KEY")

    # Fallback: secrets/gemini_api_key.txt
    if not api_key:
        secrets_dir = PROJECT_ROOT / "secrets"
        secret_file = secrets_dir / "gemini_api_key.txt"

        if secret_file.exists():
            try:
                api_key = secret_file.read_text(encoding="utf-8").strip()
                if api_key:
                    print(f"[summarizer] Loaded Gemini API key from {secret_file}")
                else:
                    raise RuntimeError("gemini_api_key.txt is empty.")
            except Exception as e:
                raise RuntimeError(f"Failed reading Gemini API key file: {e}")
        else:
            raise RuntimeError(
                "GEMINI_API_KEY is not set and gemini_api_key.txt does not exist.\n"
                f"Expected file: {secret_file}"
            )

    genai.configure(api_key=api_key)


def generate_summary(prompt: str) -> str:
    model = genai.GenerativeModel(GEMINI_MODEL)

    # retry logic for 429
    for attempt in range(5):
        try:
            response = model.generate_content(prompt)
            return response.text if hasattr(response, "text") else str(response)

        except Exception as e:
            msg = str(e)
            if "429" in msg or "quota" in msg.lower():
                sleep_s = 6 + attempt * 3
                print(f"[warn] Gemini quota hit. Retrying in {sleep_s} seconds...")
                time.sleep(sleep_s)
                continue
            raise

    raise RuntimeError("Gemini failed after retries.")


# ============================================================
#                SAVE OUTPUTS
# ============================================================

def save_markdown(summary_text: str, reports_dir: Path = REPORTS_DIR) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    path = reports_dir / f"daily_business_summary_{date_str}.md"
    with path.open("w", encoding="utf-8") as f:
        f.write("# Daily Business Summary\n\n")
        f.write(f"_Generated at: {datetime.utcnow().isoformat()}Z_\n\n")
        f.write(summary_text)
    return path


def save_txt(summary_text: str, reports_dir: Path = REPORTS_DIR) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "daily_summary.txt"
    with path.open("w", encoding="utf-8") as f:
        f.write(summary_text)
    return path


# ============================================================
#                MAIN ENTRYPOINT
# ============================================================

def run_summarizer() -> None:
    print("[info] Configuring Gemini client...")
    configure_gemini()

    print("[info] Loading metrics JSON...")
    payload = load_metrics()

    print("[info] Building LLM prompt (token-safe)...")
    prompt = build_prompt(payload)

    print("[info] Generating business summary with Gemini...")
    summary = generate_summary(prompt)

    print("[info] Saving Markdown + TXT reports...")
    md_path = save_markdown(summary)
    txt_path = save_txt(summary)

    print(f"[info] Markdown report: {md_path}")
    print(f"[info] TXT summary:     {txt_path}")

    print("\n===== SUMMARY PREVIEW (first 1200 chars) =====\n")
    print(summary[:1200])


if __name__ == "__main__":
    run_summarizer()