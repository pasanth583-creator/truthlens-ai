# Transformer Model Selection

## Environment Summary
- **Hardware Profile**: Dependent on local compute (CPU vs. GPU)
- **Dataset Size**: ~31,000 training examples, ~6,700 validation examples
- **Target Classes**: 3 (Reliable, Misleading, False)

## Candidate Models Considered
1. **BERT (bert-base-uncased)**
   - *Pros*: Solid baseline, widely supported.
   - *Cons*: Slightly outdated compared to RoBERTa; sub-optimal pretraining.
2. **RoBERTa (roberta-base)**
   - *Pros*: Significantly better performance on NLP tasks, robust pre-training, handles nuanced text (like fake news) better than BERT.
   - *Cons*: Slightly higher memory requirement.
3. **DeBERTa (deberta-v3-base)**
   - *Pros*: State-of-the-art for its size, disentangled attention mechanism.
   - *Cons*: Slower to train, higher memory footprint which might cause OOM on limited hardware.
4. **DistilBERT (distilbert-base-uncased)**
   - *Pros*: Fast, lightweight, CPU-friendly.
   - *Cons*: Lower accuracy ceiling compared to RoBERTa.

## Final Selection: `roberta-base` (with DistilBERT as CPU fallback)
Given the dataset size (~31k train), **RoBERTa (roberta-base)** is the most practical choice. It offers an excellent tradeoff between training time, memory requirements, and accuracy potential. If the environment check reveals that only CPU is available (or a low-VRAM GPU), the script will automatically fallback or utilize gradient accumulation with `roberta-base`, keeping a reasonable batch size (e.g., 8 or 16).

## Tokenization Strategy
- **Tokenizer**: `RobertaTokenizerFast`
- **Max Sequence Length**: 128 (to maintain training speed and fit in memory, as most claim sentences and short articles fit well within this bound).
- **Padding/Truncation**: True, targeting the max length.
