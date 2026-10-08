# Transformer Model Report

- **Model**: distilbert-base-uncased
- **Test Accuracy**: 0.4660
- **Test Macro F1**: 0.3933
- **Test Weighted F1**: 0.4341

## Per-Class Metrics
- **False**: Precision: 0.4545, Recall: 0.0909, F1: 0.1515
- **Misleading**: Precision: 0.4575, Recall: 0.5594, F1: 0.5033
- **Reliable**: Precision: 0.4762, Recall: 0.5851, F1: 0.5251

## Confusion Matrix
```
[[10, 64, 36], [4, 113, 85], [8, 70, 110]]
```