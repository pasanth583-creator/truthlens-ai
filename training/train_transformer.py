import os
import torch
import pandas as pd
import json
import numpy as np
from pathlib import Path
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report, confusion_matrix, f1_score
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    Trainer,
    TrainingArguments,
    EarlyStoppingCallback
)

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models" / "transformer"

TRAIN_PATH = DATA_DIR / "train.csv"
VAL_PATH = DATA_DIR / "validation.csv"
TEST_PATH = DATA_DIR / "test.csv"

# Since GPU is unavailable, we use a lighter model
MODEL_NAME = "distilbert-base-uncased"
MAX_LENGTH = 128

class TextDataset(torch.utils.data.Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __getitem__(self, idx):
        item = {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
        item['labels'] = torch.tensor(self.labels[idx])
        return item

    def __len__(self):
        return len(self.labels)

def compute_metrics(pred):
    labels = pred.label_ids
    preds = pred.predictions.argmax(-1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average='macro', zero_division=0)
    acc = accuracy_score(labels, preds)
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall': recall
    }

def main():
    print("Loading data...")
    train_df = pd.read_csv(TRAIN_PATH).dropna(subset=['text', 'label'])
    val_df = pd.read_csv(VAL_PATH).dropna(subset=['text', 'label'])
    test_df = pd.read_csv(TEST_PATH).dropna(subset=['text', 'label'])
    
    # To make CPU training feasible, we subsample the data
    print("CPU detected. Subsampling data for feasible training time...")
    train_df = train_df.sample(n=min(2000, len(train_df)), random_state=42)
    val_df = val_df.sample(n=min(500, len(val_df)), random_state=42)
    test_df = test_df.sample(n=min(500, len(test_df)), random_state=42)

    unique_labels = sorted(train_df['label'].unique().tolist())
    label2id = {label: i for i, label in enumerate(unique_labels)}
    id2label = {i: label for label, i in label2id.items()}
    
    print(f"Classes: {unique_labels}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    
    def tokenize(df):
        return tokenizer(
            df['text'].tolist(),
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH
        )

    print("Tokenizing...")
    train_encodings = tokenize(train_df)
    val_encodings = tokenize(val_df)
    test_encodings = tokenize(test_df)
    
    train_dataset = TextDataset(train_encodings, [label2id[l] for l in train_df['label']])
    val_dataset = TextDataset(val_encodings, [label2id[l] for l in val_df['label']])
    test_dataset = TextDataset(test_encodings, [label2id[l] for l in test_df['label']])

    print("Loading model...")
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(unique_labels),
        id2label=id2label,
        label2id=label2id
    )

    training_args = TrainingArguments(
        output_dir='./results',
        num_train_epochs=2,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        warmup_steps=50,
        weight_decay=0.01,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        use_cpu=True, # Force CPU mode for clarity
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=1)]
    )

    print("Training Transformer...")
    trainer.train()

    print("Evaluating on test set...")
    test_results = trainer.predict(test_dataset)
    
    preds = test_results.predictions.argmax(-1)
    labels = test_results.label_ids
    
    acc = accuracy_score(labels, preds)
    macro_f1 = f1_score(labels, preds, average='macro', zero_division=0)
    weighted_f1 = f1_score(labels, preds, average='weighted', zero_division=0)
    
    report = classification_report(labels, preds, target_names=unique_labels, output_dict=True, zero_division=0)
    cm = confusion_matrix(labels, preds)
    
    metrics_dict = {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "classification_report": report,
        "confusion_matrix": cm.tolist()
    }
    
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "transformer_results.json", "w") as f:
        json.dump(metrics_dict, f, indent=4)
        
    md_lines = [
        "# Transformer Model Report",
        "",
        f"- **Model**: {MODEL_NAME}",
        f"- **Test Accuracy**: {acc:.4f}",
        f"- **Test Macro F1**: {macro_f1:.4f}",
        f"- **Test Weighted F1**: {weighted_f1:.4f}",
        "",
        "## Per-Class Metrics",
    ]
    
    for cls in unique_labels:
        if cls in report:
            md_lines.append(f"- **{cls}**: Precision: {report[cls]['precision']:.4f}, Recall: {report[cls]['recall']:.4f}, F1: {report[cls]['f1-score']:.4f}")
            
    md_lines.extend([
        "",
        "## Confusion Matrix",
        "```",
        str(cm.tolist()),
        "```"
    ])
    
    with open(REPORTS_DIR / "transformer_report.md", "w") as f:
        f.write("\n".join(md_lines))
        
    print("Saving model...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(MODELS_DIR))
    tokenizer.save_pretrained(str(MODELS_DIR))
    
    print("=" * 40)
    print("PHASE 4 STATUS: COMPLETE")
    print("=" * 40)
    print(f"Test Accuracy: {acc:.4f}")
    print(f"Test Macro F1: {macro_f1:.4f}")
    print(f"Test Weighted F1: {weighted_f1:.4f}")

if __name__ == "__main__":
    main()
