#!/usr/bin/env bash
set -euo pipefail

# Load Gemini API key (DO NOT hardcode in production)
export GEMINI_API_KEY="AIzaSyAJP6b2mGy63wA31mGSuSF0u-SCNuKmGfw"

echo "Running daily marketing pipeline..."

# Option A: using uv (recommended)
uv run -m pipeline.run_daily

# Option B: venv Python
# source .venv/bin/activate
# python -m pipeline.run_daily

echo "Done."
