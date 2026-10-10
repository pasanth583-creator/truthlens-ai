# TruthLens AI — Explainable Fake-News Detection System

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Framework](https://img.shields.io/badge/framework-Flask%203.0%2B-green.svg)](https://flask.palletsprojects.com/)
[![NLP Model](https://img.shields.io/badge/model-DistilBERT-orange.svg)](https://huggingface.co/distilbert-base-uncased)
[![Explainability](https://img.shields.io/badge/XAI-Integrated%20Gradients-purple.svg)](https://captum.ai/)
[![Tests](https://img.shields.io/badge/tests-31%20passed-brightgreen.svg)]()

> **TruthLens AI** is an explainable fake-news detection and verification system that combines transformer-based NLP classification with Integrated Gradients attribution, live external evidence retrieval, and a dual-signal decision matrix.

---

## 1. Problem Statement

In an increasingly decentralized information ecosystem, determining whether a public statement or news claim is **reliable**, **misleading**, **false**, or **insufficiently supported** is a major societal challenge. 

Traditional approaches suffer from critical flaws:
- **Opaque Black-Box Classifiers**: Predict labels without explaining which linguistic cues triggered the decision.
- **Unchecked Hallucinations**: Classifiers often rely on surface sensationalism rather than verified facts.
- **Binary Oversimplification**: Systems frequently force nuanced or unverifiable statements into rigid true/false buckets.

---

## 2. The TruthLens AI Solution

TruthLens AI solves these challenges through a hybrid, explainable architecture:
1. **Fine-Tuned Transformer**: Employs `distilbert-base-uncased` fine-tuned for 3-way nuance classification (`False`, `Misleading`, `Reliable`).
2. **Integrated Gradients Explainability**: Mathematically computes subword and phrase-level feature attributions so users see exactly which tokens influenced the model.
3. **Live Evidence Retrieval**: Queries authoritative encyclopedic knowledge in real time via Wikipedia's public MediaWiki API (with support for Google Fact Check Tools).
4. **Dual-Signal Verification Engine**: Cross-references linguistic predictions against external evidence to flag contradictions and trigger **Conflicting Signals** alerts when facts disagree with surface style.
5. **Persistent Audit History**: Automatically stores every analysis in an SQLite database for transparency and historical review.

---

## 3. Core Workflow

```
User Claim
    ↓
NLP Classification (DistilBERT)
    ↓
Explainability (Integrated Gradients)
    ↓
Evidence Retrieval (Wikipedia API)
    ↓
Verification (Dual-Signal Decision Matrix)
    ↓
Human-Readable Result & Persistent Audit Trail
```

---

## 4. Key Features

- **3-Class Classification**: Discerning categorization across `False`, `Misleading`, and `Reliable`.
- **Calibrated Model Confidence**: Softmax probability distributions across all three classes with low-confidence (< 60%) warning indicators.
- **Integrated Gradients Attribution**: Highlighting specific phrases that drove model decisions.
- **Live Evidence Retrieval**: Retrieval of external sources with snippet extraction, domain credibility scoring, and stance detection (`supports`, `contradicts`, `neutral`).
- **Conflict Detection Engine**: Identifies divergences between model predictions and factual evidence.
- **Persistent History Log**: Complete audit trail of past analyses powered by SQLAlchemy and SQLite.
- **REST API & Modern Web UI**: Fast JSON API alongside a responsive, dark-mode web interface.

---

## 5. Dataset & Corpus Details

The dataset was curated from established public fake-news and fact-checking corpora (LIAR and TruthSeeker benchmarks):

- **Clean Corpus Size**: **11,718 unique records**
- **Data Splits**:
  - **Train**: 8,202 samples (70%)
  - **Validation**: 1,758 samples (15%)
  - **Test**: 1,758 samples (15%)
- **Supervised Classes**: `False`, `Misleading`, `Reliable`

> **Note on Unverifiable Claims**: Genuine "Unverifiable" ground truth was not present in the source training corpora. Consequently, **Unverified / Insufficient Evidence** is modeled as a retrieval verification outcome rather than an artificial supervised ML class.

---

## 6. Models & Experimental Comparison

We evaluated two distinct architectures:
1. **Baseline Model**: TF-IDF Vectorizer + Logistic Regression (trained on the full 8,202 sample training split).
2. **Transformer Model**: `distilbert-base-uncased` fine-tuned with cross-entropy loss.

### Experimental Limitation Disclosure
Due to local CPU training constraints, the DistilBERT experiment was trained on a subset of **2,000 training samples**, with **500 validation samples** and **500 test samples**, whereas the baseline was trained on the full dataset. As a result, this comparison is not a matched full-data benchmark, and we do not claim DistilBERT definitively outperforms the baseline across full-corpus training.

---

## 7. Verified Performance Metrics

The metrics below reflect the verified experimental results from project evaluation reports:

| Metric | Baseline (TF-IDF + LogReg) | DistilBERT Transformer |
|---|---|---|
| **Training Split Size** | 8,202 samples (Full) | 2,000 samples (CPU subset) |
| **Validation Accuracy** | 0.4630 | **0.4780** |
| **Validation Macro F1** | 0.3969 | **0.4102** |
| **Test Accuracy** | 0.4602 | **0.4660** |
| **Test Macro F1** | **0.3993** | 0.3933 |
| **Test Weighted F1** | **0.4373** | 0.4341 |

### Production Model Selection
`distilbert-base-uncased` was provisionally selected as the primary production classifier because it demonstrated superior validation Macro F1 (+0.0133) and validation accuracy (+0.0150), alongside rich subword embedding representations required for gradient-based feature attribution.

---

## 8. Explainability (Integrated Gradients)

TruthLens AI implements **Integrated Gradients** to provide token-level feature attribution:
- Computes gradients of the predicted class output with respect to the input word embeddings along a linear interpolation path from a baseline zero-embedding.
- Aggregates subwords into human-readable phrases.

> **Responsible AI Principle**: Model attribution is an explanation of **model behavior**, not proof of factual truth. High attribution on a word indicates that the token strongly influenced the classifier's internal representation.

---

## 9. Evidence Retrieval & Stance Detection

- **Active Provider**: Wikipedia Public MediaWiki Search API.
- **Optional / Configurable Provider**: Google Fact Check Tools (ClaimReview) API (available when `GOOGLE_FACT_CHECK_API_KEY` is provided).
- **Retrieval Pipeline**: Extracts core assertions, executes rate-limited search, filters snippets for authority domains, and classifies source relation (`supports`, `contradicts`, `neutral`).

---

## 10. Verification Decision Matrix

The verification engine synthesizes model prediction and evidence retrieval into explicit verdict states:

| Classifier Prediction | Evidence Status | Verification Result |
|---|---|---|
| False / Misleading | Contradicting | **Likely False** / Potentially False (if low confidence) |
| Reliable | Supporting | **Supported** / Provisionally Supported (if low confidence) |
| False / Misleading | Supporting | **Conflicting Signals Alert** (Evidence supports assertion) |
| Reliable | Contradicting | **Conflicting Signals Alert** (Evidence refutes assertion) |
| Any | Insufficient | **Unverified / Insufficient Evidence** |

---

## 11. REST API Reference

### Health Check: `GET /api/health`
```bash
curl http://127.0.0.1:5000/api/health
```
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model": "distilbert-base-uncased",
  "classes": ["False", "Misleading", "Reliable"],
  "evidence_provider": "Wikipedia (Public API)",
  "version": "1.0.0"
}
```

### Analyze Claim: `POST /api/analyze`
```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Drinking lemon water cures all forms of cancer."}'
```
```json
{
  "success": true,
  "analysis_id": 1,
  "analysis": {
    "prediction": { "label": "False", "confidence": 0.8421 },
    "probabilities": { "False": 0.8421, "Misleading": 0.1132, "Reliable": 0.0447 },
    "verification": { "status": "LIKELY_FALSE", "result": "Likely False -- retrieved evidence contradicts the claim." }
  }
}
```

*(See [docs/API.md](docs/API.md) for full endpoint specifications).*

---

## 12. Installation & Setup (Windows)

### Prerequisites
- Python 3.10+
- Git

### Setup Steps
```powershell
# 1. Clone repository & navigate to project directory
cd truthlens-ai

# 2. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Configure environment variables
copy .env.example .env
```

---

## 13. Running the Application

Start the Flask development server:
```powershell
python app.py
```
Open your web browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 14. Running Tests

Run the full automated test suite (31 unit and integration tests covering API endpoints, web routes, and database persistence):

```powershell
pytest -q
```
*Alternative via standard unittest:*
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

**Verified Test Result**: `31 passed in ~6.0s`.

---

## 15. Responsible AI & System Limitations

TruthLens AI is designed strictly as a **decision-support tool** for researchers, journalists, and citizens:
- **Predictions Are Not Factual Certainty**: The classifier identifies statistical patterns in language, not ground truth.
- **Evidence Retrieval Coverage**: Wikipedia and search APIs do not index all world events or newly breaking news.
- **Low-Confidence Transparency**: Predictions with confidence below 60% are flagged as low confidence.
- **Human Oversight**: In all cases involving **Conflicting Signals** or **Insufficient Evidence**, human verification is essential.

---

## 16. Documentation Index

- [Architecture & Data Flow](docs/ARCHITECTURE.md)
- [Hackathon Demo & Presentation Guide](docs/DEMO_GUIDE.md)
- [REST API Reference](docs/API.md)
- [Model Comparison Report](reports/model_comparison_report.md)
- [Explainability Report](reports/explainability_report.md)
- [Evidence Retrieval Report](reports/evidence_retrieval_report.md)
