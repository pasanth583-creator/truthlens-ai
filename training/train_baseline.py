import pandas as pd
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    f1_score,
    classification_report,
    confusion_matrix,
)
import joblib
import json
import time

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models" / "baseline"

TRAIN_PATH = DATA_DIR / "train.csv"
VAL_PATH = DATA_DIR / "validation.csv"
TEST_PATH = DATA_DIR / "test.csv"

def load_data(path: Path):
    df = pd.read_csv(path)
    # Ensure a column named 'text' exists
    if "text" not in df.columns:
        for col in ["content", "article", "title"]:
            if col in df.columns:
                df = df.rename(columns={col: "text"})
                break
    
    df['text'] = df['text'].fillna('')
    df = df.dropna(subset=['label'])
    return df["text"].astype(str).tolist(), df["label"].tolist()

def evaluate(y_true, y_pred, labels):
    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average=None, zero_division=0
    )
    macro_f1 = f1_score(y_true, y_pred, average='macro', zero_division=0)
    weighted_f1 = f1_score(y_true, y_pred, average='weighted', zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    report = classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0)
    
    return {
        "accuracy": accuracy,
        "per_class": {str(label): {"precision": p, "recall": r, "f1": f} for label, p, r, f in zip(labels, precision, recall, f1)},
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
    }

def main():
    print("Loading data...")
    X_train, y_train = load_data(TRAIN_PATH)
    X_val, y_val = load_data(VAL_PATH)
    X_test, y_test = load_data(TEST_PATH)
    
    class_labels = sorted(list(set(y_train) | set(y_val) | set(y_test)))

    print(f"Train size: {len(X_train)}")
    print(f"Validation size: {len(X_val)}")
    print(f"Test size: {len(X_test)}")
    print(f"Classes found: {class_labels}")

    print("Vectorizing...")
    start_time = time.time()
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        sublinear_tf=True
    )
    
    # Fit ONLY on train
    X_train_tfidf = vectorizer.fit_transform(X_train)
    X_val_tfidf = vectorizer.transform(X_val)
    X_test_tfidf = vectorizer.transform(X_test)

    print("Training Logistic Regression...")
    clf = LogisticRegression(max_iter=2000, random_state=42)
    clf.fit(X_train_tfidf, y_train)

    train_time = time.time() - start_time

    print("Evaluating...")
    val_pred = clf.predict(X_val_tfidf)
    val_metrics = evaluate(y_val, val_pred, class_labels)
    
    test_pred = clf.predict(X_test_tfidf)
    test_metrics = evaluate(y_test, test_pred, class_labels)

    # Save reports
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    md_lines = [
        "# Baseline Model Report",
        "",
        "## Dataset Sizes",
        f"- Train: {len(X_train)}",
        f"- Validation: {len(X_val)}",
        f"- Test: {len(X_test)}",
        "",
        "## Target Classes",
        f"- {', '.join(map(str, class_labels))}",
        "",
        "## Configurations",
        "- **TF-IDF**: ngram_range=(1,2), min_df=2, max_df=0.95, sublinear_tf=True",
        "- **Logistic Regression**: max_iter=2000, random_state=42",
        "",
        "## Validation Metrics",
        f"- Accuracy: {val_metrics['accuracy']:.4f}",
        f"- Macro F1: {val_metrics['macro_f1']:.4f}",
        f"- Weighted F1: {val_metrics['weighted_f1']:.4f}",
        "",
        "### Per-class metrics"
    ]
    for label, stats in val_metrics["per_class"].items():
        md_lines.append(f"- **{label}** - Precision: {stats['precision']:.4f}, Recall: {stats['recall']:.4f}, F1: {stats['f1']:.4f}")
    
    md_lines.extend([
        "",
        "## Test Metrics",
        f"- Accuracy: {test_metrics['accuracy']:.4f}",
        f"- Macro F1: {test_metrics['macro_f1']:.4f}",
        f"- Weighted F1: {test_metrics['weighted_f1']:.4f}",
        "",
        "### Per-class metrics"
    ])
    for label, stats in test_metrics["per_class"].items():
        md_lines.append(f"- **{label}** - Precision: {stats['precision']:.4f}, Recall: {stats['recall']:.4f}, F1: {stats['f1']:.4f}")
    
    md_lines.extend([
        "",
        "## Confusion Matrix (Test)",
        "```",
        str(test_metrics['confusion_matrix']),
        "```",
        "",
        "## Training Time",
        f"{train_time:.2f} seconds",
        "",
        "## Leakage Verification Status",
        "Data was supposedly cleaned, but if accuracy is 1.0000, the dataset still only has a single class (Unverifiable) or contains duplicate leakage.",
        "",
        "## Final Conclusion",
        "If results are suspiciously high, verify dataset integrity immediately."
    ])

    report_path = REPORTS_DIR / "baseline_model_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # Save model artifacts
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, MODELS_DIR / "tfidf_vectorizer.pkl")
    joblib.dump(clf, MODELS_DIR / "logistic_regression.pkl")
    
    with open(MODELS_DIR / "classes.json", "w", encoding="utf-8") as f:
        json.dump(class_labels, f)

    print("=" * 40)
    print("PHASE 3 BASELINE MODEL")
    print("=" * 40)
    print(f"Validation Accuracy: {val_metrics['accuracy']:.4f}")
    print(f"Validation Macro F1: {val_metrics['macro_f1']:.4f}")
    print()
    print(f"Test Accuracy: {test_metrics['accuracy']:.4f}")
    print(f"Test Macro F1: {test_metrics['macro_f1']:.4f}")
    print(f"Test Weighted F1: {test_metrics['weighted_f1']:.4f}")
    print()
    print("Classes:")
    print(class_labels)
    print()
    print(f"Model saved:\n{MODELS_DIR}")
    print(f"Report saved:\n{report_path}")
    print()
    print("PHASE 3 STATUS: COMPLETE")

if __name__ == "__main__":
    main()
