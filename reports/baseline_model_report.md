# Baseline Model Report

## Dataset Sizes
- Train: 8202
- Validation: 1758
- Test: 1758

## Target Classes
- False, Misleading, Reliable

## Configurations
- **TF-IDF**: ngram_range=(1,2), min_df=2, max_df=0.95, sublinear_tf=True
- **Logistic Regression**: max_iter=2000, random_state=42

## Validation Metrics
- Accuracy: 0.4630
- Macro F1: 0.3969
- Weighted F1: 0.4366

### Per-class metrics
- **False** - Precision: 0.4556, Recall: 0.1096, F1: 0.1767
- **Misleading** - Precision: 0.4438, Recall: 0.5749, F1: 0.5009
- **Reliable** - Precision: 0.4874, Recall: 0.5414, F1: 0.5130

## Test Metrics
- Accuracy: 0.4602
- Macro F1: 0.3993
- Weighted F1: 0.4373

### Per-class metrics
- **False** - Precision: 0.3884, Recall: 0.1257, F1: 0.1899
- **Misleading** - Precision: 0.4602, Recall: 0.5783, F1: 0.5125
- **Reliable** - Precision: 0.4718, Recall: 0.5215, F1: 0.4954

## Confusion Matrix (Test)
```
[[47, 187, 140], [45, 410, 254], [29, 294, 352]]
```

## Training Time
0.70 seconds

## Leakage Verification Status
Data was supposedly cleaned, but if accuracy is 1.0000, the dataset still only has a single class (Unverifiable) or contains duplicate leakage.

## Final Conclusion
If results are suspiciously high, verify dataset integrity immediately.