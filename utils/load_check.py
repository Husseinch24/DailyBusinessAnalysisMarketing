import json
import pandas as pd
from tqdm import tqdm
import os

# NEW: import correct data directory from settings
from config.settings import DATA_DIR

FILES = [
    "Baby_Products.jsonl",
    "Video_Games.jsonl"
]

SAMPLE_SIZE = 50000   # number of rows to sample safely


def load_sample(path, n_rows):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(tqdm(f, desc=f"Reading sample from {path}")):
            if i >= n_rows:
                break
            rows.append(json.loads(line))
    return pd.DataFrame(rows)


def explore_dataframe(df, name):
    print("\n" + "=" * 60)
    print(f"DATASET: {name}")
    print("=" * 60)

    print("\nShape:", df.shape)
    print("\nColumns:")
    print(df.columns.tolist())

    print("\nSample rows:")
    print(df.head())

    print("\nMissing values:")
    print(df.isna().sum())

    print("\nBasic numeric statistics:")
    print(df.describe(include="all"))

    print("\n" + "=" * 60 + "\n")


# -------------------------
# PROCESS FILES
# -------------------------
def main():
    for filename in FILES:
        full_path = os.path.join(DATA_DIR, filename)

        print(f"\n=== Loading sample from {filename} ===")
        df = load_sample(full_path, SAMPLE_SIZE)

        explore_dataframe(df, filename)


if __name__ == "__main__":
    main()