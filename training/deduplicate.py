import os
import pandas as pd
from pathlib import Path

def deduplicate_file(src_path: Path, dest_path: Path):
    """Read a CSV/TSV file, drop exact duplicate rows, and write the cleaned version.
    Preserves original column order and data types.
    """
    if not src_path.exists():
        print(f"[WARN] Source file not found: {src_path}")
        return
    sep = "\t" if src_path.suffix.lower() == ".tsv" else ","
    df = pd.read_csv(src_path, sep=sep, encoding="utf-8", low_memory=False)
    original_rows = len(df)
    df_clean = df.drop_duplicates()
    cleaned_rows = len(df_clean)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(dest_path, index=False, sep=sep, encoding="utf-8")
    print(f"[INFO] {src_path.name}: {original_rows} -> {cleaned_rows} rows (removed {original_rows - cleaned_rows} duplicates)")

def main():
    # project_root is the repository root (truthlens-ai)
    project_root = Path(__file__).resolve().parents[1]  # truthlens-ai
    raw_dir = project_root / "data" / "raw"
    processed_dir = project_root / "data" / "processed"
    for dataset_dir in raw_dir.iterdir():
        if not dataset_dir.is_dir():
            continue
        for file_path in dataset_dir.iterdir():
            if file_path.suffix.lower() not in {".csv", ".tsv"}:
                continue
            dest_subdir = processed_dir / dataset_dir.name
            dest_name = f"{file_path.stem}_clean{file_path.suffix}"
            dest_path = dest_subdir / dest_name
            deduplicate_file(file_path, dest_path)

if __name__ == "__main__":
    main()
