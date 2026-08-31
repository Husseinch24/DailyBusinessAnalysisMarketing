from pathlib import Path

# -------------------------------------------------------------------
# Base project path (root of the repository)
# -------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# -------------------------------------------------------------------
# Data paths
# -------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"

DAILY_BATCH_PATH = DATA_DIR / "daily_batch.parquet"
METRICS_PATH = DATA_DIR / "daily_metrics.json"

# -------------------------------------------------------------------
# Reports paths
# -------------------------------------------------------------------
REPORTS_DIR = PROJECT_ROOT / "reports"

# -------------------------------------------------------------------
# Timestamp column used across ingestion/analysis
# -------------------------------------------------------------------
TIMESTAMP_COL = "timestamp"

# -------------------------------------------------------------------
# Gemini model used for summarization and product insights
# -------------------------------------------------------------------
GEMINI_MODEL = "gemini-2.5-flash"