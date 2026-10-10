# TruthLens AI — System Architecture

This document describes the high-level architecture, module responsibilities, data flow, and design decisions of **TruthLens AI** (Explainable Fake-News Detection System).

---

## 1. High-Level Architecture Diagram

```
                       ┌─────────────────────────────────────────┐
                       │           Web Browser / Client          │
                       │    (Responsive UI: HTML5, CSS3, JS)     │
                       └───────────────────┬─────────────────────┘
                                           │
                                  HTTP GET / POST / API
                                           │
                       ┌───────────────────▼─────────────────────┐
                       │          Flask Web Application          │
                       │               (`app.py`)                │
                       │  - Route handling & request validation  │
                       │  - REST API & UI template rendering     │
                       └───────────────────┬─────────────────────┘
                                           │
                                           │ dispatches claim text
                                           ▼
                       ┌─────────────────────────────────────────┐
                       │        Core Verification Engine         │
                       │     (`services/verification.py`)        │
                       └──────┬────────────┬─────────────┬───────┘
                              │            │             │
               ┌──────────────┘            │             └──────────────┐
               ▼                           ▼                            ▼
   ┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
   │    Claim Extractor    │   │  DistilBERT Classifier│   │   Evidence Retrieval  │
   │(`claim_extractor.py`) │   │   & Explainer Engine  │   │   (`evidence.py`)     │
   │ - Strips attribution  │   │  (`explainer.py` &    │   │ - Wikipedia Search API│
   │ - Extracts core claim │   │`transformer_model.py`)│   │ - Google Fact Check   │
   │ - Formulates search q │   │ - DistilBERT 3-class  │   │   (Configurable)      │
   └───────────────────────┘   │ - Integrated Gradients│   │ - Source ranking &    │
                               │   token attribution   │   │   relation heuristics │
                               └───────────┬───────────┘   └───────────┬───────────┘
                                           │                           │
                                           └─────────────┬─────────────┘
                                                         │
                                                         ▼
                                       ┌───────────────────────────────────┐
                                       │       Decision Matrix Logic       │
                                       │   (`services/verification.py`)    │
                                       │ - Dual-signal synthesis           │
                                       │ - Conflict detection              │
                                       │ - Confidence threshold evaluation │
                                       └─────────────────┬─────────────────┘
                                                         │
                                                         ▼
                                       ┌───────────────────────────────────┐
                                       │     SQLite Database Persistence   │
                                       │         (`database.py`)           │
                                       │ - Stores analysis records         │
                                       │ - Preserves history & metadata    │
                                       └─────────────────┬─────────────────┘
                                                         │
                                                         ▼
                                       ┌───────────────────────────────────┐
                                       │       Result Presentation         │
                                       │ - Rich Interactive UI (`result`)  │
                                       │ - Historical Feed (`history`)     │
                                       │ - Structured JSON REST Response   │
                                       └───────────────────────────────────┘
```

---

## 2. Module & Service Responsibilities

### 2.1 Web Application Layer (`app.py`, `config.py`)
- **`app.py`**:
  - Implements the Flask application factory (`create_app`).
  - Registers Web UI endpoints (`/`, `/analyze`, `/result/<id>`, `/history`, `/history/<id>`, `/about`).
  - Registers REST API endpoints (`/api/health`, `/api/analyze`).
  - Handles request sanitization, input validation (5 to 10,000 characters), exception logging, and structured error responses.
- **`config.py`**:
  - Centralizes configuration parameters for development, testing, and production environments.
  - Manages database URI, model paths, input constraints, and optional API credentials.

### 2.2 Input Validation (`utils/validators.py`)
- Strips harmful control characters and normalizes whitespace.
- Enforces character bounds ($5 \le \text{length} \le 10000$).
- Detects empty or whitespace-only inputs and returns user-friendly error messages.

### 2.3 Claim Extraction (`services/claim_extractor.py`)
- Analyzes incoming text to isolate the core factual assertion.
- Removes reporting prefixes (e.g., *"Reports claim that..."*, *"According to social media posts..."*).
- Formulates clean, keyword-dense queries optimized for external knowledge retrieval.

### 2.4 NLP Classification & Explainability (`services/explainer.py`, `services/transformer_model.py`)
- **`transformer_model.py`**:
  - Wraps PyTorch and HuggingFace `distilbert-base-uncased` fine-tuned for 3-class classification (`False`, `Misleading`, `Reliable`).
  - Computes class logits and softmax probabilities.
- **`explainer.py`**:
  - Computes word-level and subword-level feature attribution using **Integrated Gradients** (or gradient $\times$ embedding approximation).
  - Groups attributed subword tokens into coherent phrases.
  - Classifies token direction as supporting or challenging the predicted class.
  - Applies a confidence threshold ($0.60$) to classify model certainty.

### 2.5 Evidence Retrieval Engine (`services/evidence.py`)
- **Provider Architecture**:
  - `WikipediaEvidenceProvider`: Uses Wikipedia's public MediaWiki search API to retrieve encyclopedic summaries and authoritative article links. Rate-limited and cached in-memory.
  - `GoogleFactCheckProvider`: Configurable provider utilizing the Google Fact Check Tools ClaimReview API when an API key is supplied.
- **Relevance Scoring & Relation Analysis**:
  - Computes keyword overlap between claims and retrieved snippets with authority domain weighting.
  - Analyzes contextual negation and corroboration patterns (`contradicts`, `supports`, `neutral`).
  - Synthesizes an overall evidence status: `supporting`, `contradicting`, or `insufficient`.

### 2.6 Dual-Signal Verification & Decision Synthesis (`services/verification.py`)
Synthesizes the neural classifier's prediction with the external evidence status using a deterministic decision matrix:

| Model Prediction | Evidence Status | Verification Outcome | Conflict Detected |
|---|---|---|---|
| False / Misleading | Contradicting | **Likely False** / Potentially False (if low confidence) | No |
| Reliable | Supporting | **Supported** / Provisionally Supported (if low confidence) | No |
| False / Misleading | Supporting | **Conflicting Signals** (Evidence corroborates assertion) | **Yes** |
| Reliable | Contradicting | **Conflicting Signals** (Evidence refutes assertion) | **Yes** |
| Any | Insufficient | **Unverified / Insufficient Evidence** | No |

### 2.7 Persistence Layer (`database.py`)
- Uses **Flask-SQLAlchemy** with an SQLite backend (`database/truthlens.db`).
- Stores complete verification runs (`Analysis` model) including:
  - Input text, predicted label, confidence, verification status, evidence status.
  - Serialized JSON probabilities, extracted important phrases, evidence sources, summaries, and conflict flags.
- Provides serialization methods `to_dict()` and `to_summary_dict()`.

### 2.8 Presentation Layer (`templates/`, `static/`)
- **`templates/base.html`**: Shared responsive layout with dark navy/slate aesthetic, accessible navigation, and footer.
- **`templates/index.html`**: Landing hero with system value proposition, core metrics, workflow pillars, and direct CTA.
- **`templates/analyze.html`**: Claim input form with character counter, quick-load sample claim pills, and live loading state.
- **`templates/result.html`**: Full analytical report showing verification verdict badges, confidence breakdown bars, Integrated Gradients highlighted tokens, and external evidence cards.
- **`templates/history.html`**: Reverse-chronological table of prior analyses with status badges and detail links.
- **`templates/about.html`**: Educational methodology breakdown, dataset disclosures, and Responsible AI guidelines.
- **`static/css/style.css`**: Design tokens, glassmorphism containers, responsive grid, and badge color schemes.
- **`static/js/analyze.js`**: Dynamic form interactions, validation feedback, and sample loading.

---

## 3. Data Flow Diagram

```
User Input Form / JSON Request
            │
            ▼
    Validation Check
   (5-10,000 characters)
            │
     ┌──────┴──────────────────────┐
     ▼                             ▼
DistilBERT NLP Model        Claim Extractor
     │                             │
Softmax Probabilities       Cleaned Search Query
     │                             │
Integrated Gradients               ▼
Attribution Tokens        Evidence Retrieval (Wikipedia API)
     │                             │
     │                    Retrieved Sources & Stance
     │                             │
     └──────────────┬──────────────┘
                    ▼
          Verification Engine
       (Decision Matrix Synthesis)
                    │
                    ▼
          SQLAlchemy / SQLite
        (Persistent Record Save)
                    │
                    ▼
       Render Result HTML / JSON
```
