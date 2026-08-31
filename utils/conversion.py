import os
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.json as paj

# NEW: import your shared path config
from config.settings import DATA_DIR

FILES = [
    "Baby_Products.jsonl",
    "Video_Games.jsonl",
]


def convert_jsonl_to_parquet(input_path, output_path):
    print(f"\nConverting:\n  {input_path}\n → {output_path}")

    table = paj.read_json(
        input_path,
        read_options=pa.json.ReadOptions(block_size=1 << 20),  # read in 1MB chunks
        parse_options=pa.json.ParseOptions(explicit_schema=None),
    )

    pq.write_table(table, output_path)
    print(f"Saved Parquet: {output_path}")


def main():
    for filename in FILES:
        input_path = os.path.join(DATA_DIR, filename)
        output_path = input_path.replace(".jsonl", ".parquet")

        convert_jsonl_to_parquet(input_path, output_path)


if __name__ == "__main__":
    main()