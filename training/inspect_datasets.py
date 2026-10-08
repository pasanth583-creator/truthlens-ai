# training/inspect_datasets.py
"""Dataset inspection script for TruthLens AI Phase 2.
It scans the expected raw data folders, loads any present files, and
writes a human‑readable report to ``reports/dataset_inspection_report.txt``.
"""
import os
import pandas as pd
from pathlib import Path

def get_df(path: Path):
    """Load a CSV/TSV file with pandas.
    The function infers the separator from the extension.
    """
    if not path.exists():
        return None
    if path.suffix.lower() == ".tsv":
        return pd.read_csv(path, sep="\t", encoding="utf-8", low_memory=False)
    else:
        return pd.read_csv(path, encoding="utf-8", low_memory=False)

def inspect_file(df: pd.DataFrame, name: str):
    rows, cols = df.shape
    col_names = list(df.columns)
    dtypes = {c: str(dt) for c, dt in df.dtypes.items()}
    missing = df.isnull().sum().to_dict()
    dup_count = df.duplicated().sum()
    sample = df.head(2).to_dict(orient="records")
    # Guess label column(s)
    possible_label_cols = [c for c in df.columns if c.lower() in {"label", "target", "class", "category", "veracity", "rating"}]
    label_info = {}
    if possible_label_cols:
        label_col = possible_label_cols[0]
        unique_labels = df[label_col].dropna().unique().tolist()
        distribution = df[label_col].value_counts(dropna=False).to_dict()
        label_info = {
            "label_column": label_col,
            "unique_labels": unique_labels,
            "distribution": distribution,
        }
    return {
        "filename": name,
        "rows": rows,
        "columns": cols,
        "column_names": col_names,
        "dtypes": dtypes,
        "missing_counts": missing,
        "duplicate_rows": int(dup_count),
        "sample_records": sample,
        "label_info": label_info,
    }

def main():
    project_root = Path(__file__).resolve().parents[1]  # truthlens‑ai
    raw_dir = project_root / "data" / "raw"
    report_lines = []
    datasets = {
        "LIAR": raw_dir / "liar",
        "FakeNewsNet": raw_dir / "fakenewsnet",
        "COVID": raw_dir / "covid",
        "ISOT": raw_dir / "isot",
        "WELFake": raw_dir / "welfake",
    }
    for ds_name, ds_path in datasets.items():
        report_lines.append(f"## {ds_name} dataset")
        if not ds_path.exists():
            report_lines.append(f"*Folder not found: {ds_path}*\\n")
            continue
        files = list(ds_path.glob("*"))
        if not files:
            report_lines.append("*No files in this folder.*\\n")
            continue
        for f in files:
            if f.suffix.lower() not in {".csv", ".tsv"}:
                continue
            df = get_df(f)
            if df is None:
                report_lines.append(f"- Unable to read {f.name}\\n")
                continue
            info = inspect_file(df, f.name)
            report_lines.append(f"- **File:** {info['filename']}")
            report_lines.append(f"  - Rows: {info['rows']}")
            report_lines.append(f"  - Columns: {info['columns']}")
            report_lines.append(f"  - Column names: {', '.join(info['column_names'])}")
            report_lines.append(f"  - Dtypes: {', '.join([f'{c}:{t}' for c,t in info['dtypes'].items()])}")
            report_lines.append(f"  - Missing values per column: {info['missing_counts']}")
            report_lines.append(f"  - Duplicate rows: {info['duplicate_rows']}")
            report_lines.append(f"  - Sample records (first 2 rows):")
            for idx, rec in enumerate(info['sample_records'], start=1):
                report_lines.append(f"    {idx}: {rec}")
            if info['label_info']:
                li = info['label_info']
                report_lines.append(f"  - Detected label column: {li['label_column']}")
                report_lines.append(f"  - Unique labels: {li['unique_labels']}")
                report_lines.append(f"  - Distribution: {li['distribution']}")
            else:
                report_lines.append("  - No obvious label column detected.")
            report_lines.append("")
    # Write report
    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "dataset_inspection_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"Dataset inspection report written to {report_path}")

if __name__ == "__main__":
    main()
