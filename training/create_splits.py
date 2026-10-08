import os
import sys
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
# Ensure the project root is on PYTHONPATH so we can import the services package
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))
# Import the label‑mapping utility
from services.data_preprocessing import map_label

def load_cleaned_files(processed_dir: Path):
    """Load all *_clean.* files from the processed directory.
    Returns a single DataFrame with an added column "source_dataset".
    """
    dfs = []
    for dataset_dir in processed_dir.iterdir():
        if not dataset_dir.is_dir():
            continue
        for f in dataset_dir.iterdir():
            if f.suffix.lower() not in {".csv", ".tsv"}:
                continue
            sep = "\t" if f.suffix.lower() == ".tsv" else ","
            df = pd.read_csv(f, sep=sep, encoding="utf-8", low_memory=False)
            df["source_dataset"] = dataset_dir.name
            dfs.append(df)
    if not dfs:
        raise RuntimeError("No cleaned files found in processed directory")
    combined = pd.concat(dfs, ignore_index=True)
    return combined

def standardize_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Create a unified "label" column using map_label.
    The function looks for a column that likely contains the original label
    (e.g., "label", "class", "category", "verdict", etc.). If none is found,
    the row is marked as "Unverifiable".
    """
    possible_label_cols = [c for c in df.columns if c.lower() in {"label", "class", "category", "verdict", "rating", "truthfulness", "stance"}]
    if possible_label_cols:
        label_col = possible_label_cols[0]
        df["label"] = df[label_col].apply(map_label)
    else:
        df["label"] = "Unverifiable"
    return df

def split_and_save(df: pd.DataFrame, output_dir: Path):
    RANDOM_STATE = 42
    # Split off test set (10%)
    train_val, test = train_test_split(df, test_size=0.1, stratify=df["label"], random_state=RANDOM_STATE)
    # Split train/validation (10% of remaining for validation)
    train, val = train_test_split(train_val, test_size=0.1, stratify=train_val["label"], random_state=RANDOM_STATE)
    output_dir.mkdir(parents=True, exist_ok=True)
    train.to_csv(output_dir / "train.csv", index=False, encoding="utf-8")
    val.to_csv(output_dir / "validation.csv", index=False, encoding="utf-8")
    test.to_csv(output_dir / "test.csv", index=False, encoding="utf-8")
    print(f"[INFO] Saved splits: {len(train)} train, {len(val)} validation, {len(test)} test")

def generate_quality_report(df: pd.DataFrame, splits_dir: Path):
    report_path = splits_dir.parent.parent / "reports" / "data_quality_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Data Quality Report\n\n")
        f.write(f"Total records after cleaning: {len(df)}\n\n")
        # Overall class distribution (plain markdown table)
        f.write("## Class distribution (overall)\n")
        f.write("| Class | Count |\n|---|---|\n")
        for cls, cnt in df["label"].value_counts().items():
            f.write(f"| {cls} | {cnt} |\n")
        f.write("\n")
        # Per-split statistics
        for split_name in ["train", "validation", "test"]:
            split_path = splits_dir / f"{split_name}.csv"
            if split_path.exists():
                split_df = pd.read_csv(split_path)
                f.write(f"## {split_name.capitalize()} split – {len(split_df)} rows\n")
                f.write("| Class | Count |\n|---|---|\n")
                for cls, cnt in split_df["label"].value_counts().items():
                    f.write(f"| {cls} | {cnt} |\n")
                f.write("\n")
    print(f"[INFO] Data quality report written to {report_path}")

def main():
    project_root = Path(__file__).resolve().parents[1]
    processed_dir = project_root / "data" / "processed"
    combined_df = load_cleaned_files(processed_dir)
    combined_df = standardize_labels(combined_df)
    split_and_save(combined_df, processed_dir)
    generate_quality_report(combined_df, processed_dir)

if __name__ == "__main__":
    main()
