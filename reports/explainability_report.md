# TruthLens AI — Phase 6 Explainability Engine Report

## 1. Explainability Method
The TruthLens AI Explainability Engine employs **Integrated Gradients (Sundararajan et al., 2017)** applied directly to the continuous token embedding space of the fine-tuned Transformer model.

For an input embedding vector $x$ and a neutral reference baseline $x_0 = \mathbf{0}$ (the zero-embedding baseline), the attribution for each embedding dimension across $M$ interpolation steps is defined as:
$$\text{IG}_i(x) = (x_i - x_{0,i}) \times \frac{1}{M} \sum_{m=1}^M \frac{\partial F_c\left(x_0 + \frac{m}{M}(x - x_0)\right)}{\partial x_i}$$
where $F_c$ represents the logit activation for the predicted veracity class $c \in \{\text{False}, \text{Misleading}, \text{Reliable}\}$. The scalar token-level attribution is computed by summing across the hidden dimension ($D=768$).

---

## 2. Why It Was Selected
1. **Axiomatic Soundness**: Integrated Gradients satisfies the axioms of *Completeness* and *Implementation Invariance*, guaranteeing that the attributions account for non-linear saturation in deep networks.
2. **CPU-Friendly Execution**: Unlike sampling-based perturbation methods (such as kernel SHAP or LIME) that require hundreds of forward evaluations per prediction, Integrated Gradients achieves high attribution fidelity in just 5 gradient backward steps, executing in under 0.7 seconds on standard CPU hardware.
3. **No External Dependencies**: Operates natively on PyTorch and Hugging Face Transformers without relying on uninstalled heavy packages (`captum`, `shap`).

---

## 3. Model Used
- **Architecture**: `DistilBertForSequenceClassification` (`distilbert-base-uncased`)
- **Location**: `models/production/`
- **Output Classes**: `False`, `Misleading`, `Reliable`
- **Max Sequence Length**: 128 tokens
- **Inference Mode**: PyTorch `eval()` with gradient hooks enabled exclusively during backward attribution passes.

---

## 4. Confidence Calculation
Softmax normalization is applied across the output logits to yield mutually exclusive class probabilities summing to 1.0:
$$P(y = c \mid x) = \frac{e^{z_c}}{\sum_{j=1}^C e^{z_j}}$$
- **Confidence Score**: The model confidence equals $\max_{c} P(y = c \mid x)$.
- **Reporting Convention**: Stated strictly as **"Model Confidence: XX.X%"** rather than "factual certainty" or "proof of veracity".

---

## 5. Important Phrase Extraction & Subword Merging
DistilBERT utilizes WordPiece tokenization, which divides rare or complex vocabulary into fragments (e.g. `['romney', '##care']`). TruthLens AI resolves this through a character offset mapping pipeline:
1. **Character Offset Alignment**: Uses `return_offsets_mapping=True` to track exact span offsets in the original input string.
2. **Subword Aggregation**: Contiguous subword tokens are merged into their root words and their attributions are summed, preserving original capitalization and punctuation structure.
3. **Multi-Word N-Grams**: Contiguous word pairs that both positively reinforce the prediction are scored and merged into meaningful bigram phrases (e.g., `"Romneycare has"`, `"killed 18,000"`, `"Tennessee students"`).
4. **Noise Filtering & Normalization**: Punctuation artifacts and standalone trivial stopwords (`the`, `is`, `of`) are filtered out. Raw attribution scores are normalized to a relative importance scale from $0.05$ to $1.00$.
5. **Directional Tagging**: Each phrase is assigned a directional tag:
   - `supports_prediction`: Positive gradient alignment with the target logit.
   - `opposes_prediction`: Negative gradient counteracting the target logit.

---

## 6. Configurable Low-Confidence Handling
Predictions with marginal confidence are flagged transparently to avoid false certainty:
- **Threshold**: `EXPLANATION_CONFIDENCE_THRESHOLD = 0.60` (Configurable in `services/explainer.py`).
- **Status Classification**:
  - `confidence >= 0.60`: **"Model prediction"**
  - `confidence < 0.60`: **"Low confidence"**
- When flagged as low confidence, the explanation summary explicitly warns the user that the model's confidence is divided across competing classes.

---

## 7. Example Explanations (Evaluated Test Set Samples)

### Case 1: High Confidence Misleading Claim
- **Input**: `"Romneycare has killed 18,000 Massachusetts jobs."`
- **Prediction**: `Misleading`
- **Confidence**: 79.75% (*Model prediction*)
- **Probabilities**: False: 7.13%, Misleading: 79.75%, Reliable: 13.12%
- **Top Phrases**:
  - `"killed"` (Importance: 1.00, `supports_prediction`)
  - `"has killed"` (Importance: 1.00, `supports_prediction`)
  - `"killed 18,000"` (Importance: 1.00, `supports_prediction`)
  - `"Romneycare has"` (Importance: 0.91, `supports_prediction`)
  - `"18,000"` (Importance: 0.90, `supports_prediction`)
- **Explanation**:
  > *"The model classified this text as Misleading with 79.8% model confidence. Several phrases in the input contributed strongly to this prediction. These phrases reflect patterns learned from the training data; they do not independently establish whether the claim is factually true or false."*

### Case 2: High Confidence Reliable Report
- **Input**: `"Tennessee students now cover about 67 percent of the cost of their education at public universities, and some 60 percent at community colleges."`
- **Prediction**: `Reliable`
- **Confidence**: 66.38% (*Model prediction*)
- **Probabilities**: False: 5.59%, Misleading: 28.03%, Reliable: 66.38%
- **Top Phrases**:
  - `"Tennessee students"` (Importance: 0.66, `supports_prediction`)
  - `"Tennessee"` (Importance: 0.57, `supports_prediction`)
  - `"education"` (Importance: 0.52, `supports_prediction`)
  - `"students"` (Importance: 0.42, `supports_prediction`)
- **Explanation**:
  > *"The model classified this text as Reliable with 66.4% model confidence. Several phrases in the input contributed strongly to this prediction. These phrases reflect patterns learned from the training data; they do not independently establish whether the claim is factually true or false."*

### Case 3: Low Confidence Claim
- **Input**: `"On possibly raising the Social Security retirement age."`
- **Prediction**: `Misleading`
- **Confidence**: 39.08% (*Low confidence*)
- **Probabilities**: False: 37.72%, Misleading: 39.08%, Reliable: 23.20%
- **Top Phrases**:
  - `"Social Security"` (Importance: 1.00, `supports_prediction`)
  - `"raising the"` (Importance: 0.75, `supports_prediction`)
- **Explanation**:
  > *"The model assigned a provisional label of Misleading with 39.1% model confidence (classified as Low confidence because confidence is below the 60% threshold). The probabilities are distributed among multiple classes. These phrases reflect training associations and must not be interpreted as definitive fact-checking."*

---

## 8. Limitations
1. **Stylistic Rather Than Evidential**:
   The explainer reveals *which input words the neural network correlated with the label*. It does not explain *why the historical event did or did not take place*.
2. **Corpus Correlation Bias**:
   If specific political figures or terms occurred disproportionately in false claims during training, the gradient will highlight those names even when the specific new claim is factual.
3. **Fixed Baseline Choice**:
   Using the zero-embedding baseline represents uninformative null input, but different baseline choices (e.g., embedding of the `[MASK]` token) may cause slight variations in token attribution rankings.

---

## 9. Responsible AI & Critical Distinction

### **MODEL EXPLANATION vs. FACTUAL VERIFICATION**

| Dimension | Model Explanation (Phase 6) | Factual Verification (Phase 7+) |
|---|---|---|
| **Core Question** | *"Why did the neural network assign this label to these words?"* | *"Is this real-world claim true according to authoritative evidence?"* |
| **Data Source** | Internal model weights, activations, and token gradients. | External databases, academic sources, encyclopedias, and fact-checking archives. |
| **Mechanism** | Integrated Gradients on token embeddings. | Information retrieval, document ranking, and natural language inference (NLI). |
| **Meaning of Confidence** | The model's internal softmax distribution over learned training patterns. | Strength, consensus, and freshness of retrieved factual evidence. |
| **Limitation** | Cannot detect novel falsehoods styled in formal academic prose. | Dependent on search retrieval coverage and knowledge base freshness. |

> **RESPONSIBLE AI DISCLOSURE**:
> 
> TruthLens AI explicitly informs users that token attributions indicate mathematical influence on the classifier, not evidence of real-world veracity. Evidence-based fact-checking requires subsequent retrieval and cross-verification stages.
