# TruthLens AI — Phase 9 Flask Backend & AI Integration Report

## 1. Flask Architecture
The TruthLens AI backend is built with **Flask 3.1** following the application factory pattern (`create_app` in `app.py`). It exposes web UI routes for end users alongside clean, decoupled REST API endpoints for automated verification clients.

```
                           [Client Request]
                                  │
                                  ▼
               ┌──────────────────────────────────────┐
               │         Flask Web & REST API         │
               │   (Input Validation & Sanitization)  │
               └──────────────────┬───────────────────┘
                                  │
                                  ▼
               ┌──────────────────────────────────────┐
               │        services/verification.py      │
               └─────────┬──────────────────┬─────────┘
                         │                  │
         ┌───────────────▼────────┐  ┌──────▼────────────────┐
         │ services/explainer.py  │  │ services/evidence.py  │
         │ - DistilBERT Inference │  │ - Claim Extraction    │
         │ - Integrated Gradients │  │ - Wikipedia Search    │
         └───────────────┬────────┘  └──────┬────────────────┘
                         │                  │
                         └────────┬─────────┘
                                  ▼
               ┌──────────────────────────────────────┐
               │    Synthesis & Decision Matrix       │
               │  - Conflict Detection Banner         │
               │  - Low-Confidence Qualification      │
               └──────────────────┬───────────────────┘
                                  │
                                  ▼
               ┌──────────────────────────────────────┐
               │     Result Persistence & Response    │
               │  - SQLite Analysis Table             │
               │  - JSON / HTML Template Render       │
               └──────────────────────────────────────┘
```

---

## 2. Web UI Routes

| HTTP Method | Route | Description | Template / Response |
|---|---|---|---|
| `GET` | `/` | Application landing page detailing system capabilities and API instructions | `templates/index.html` (200 OK) |
| `GET` | `/analyze` | Submission form with sample claims and input textarea | `templates/analyze.html` (200 OK) |
| `POST` | `/analyze` | Validates input, executes verification, persists record, and redirects | `302 Redirect` &rarr; `/result/<analysis_id>` |
| `GET` | `/result/<analysis_id>` | Detailed verification report with AI prediction, evidence, and responsible AI disclosures | `templates/result.html` (200 OK or 404) |

---

## 3. REST API Structure

### `GET /api/health`
Returns backend service and model readiness without leaking file paths or internal secrets:
```json
{
  "classes": ["False", "Misleading", "Reliable"],
  "evidence_provider": "Wikipedia (Public API)",
  "model": "distilbert-base-uncased",
  "model_loaded": true,
  "status": "healthy",
  "version": "1.0.0"
}
```

### `POST /api/analyze`
**Request Payload**:
```json
{
  "text": "Scientific studies show that vaccines cause autism in children."
}
```

**Response Payload (HTTP 200)**:
```json
{
  "success": true,
  "analysis": {
    "claim": "Scientific studies show that vaccines cause autism in children",
    "prediction": {
      "confidence": 0.4392,
      "label": "Misleading"
    },
    "probabilities": {
      "False": 0.2821,
      "Misleading": 0.4392,
      "Reliable": 0.2787
    },
    "explanation": {
      "confidence_status": "Low confidence",
      "important_phrases": [
        {"direction": "supports_prediction", "importance": 1.0, "phrase": "show"},
        {"direction": "supports_prediction", "importance": 1.0, "phrase": "studies show"},
        {"direction": "supports_prediction", "importance": 0.71, "phrase": "vaccines cause"}
      ],
      "summary": "The model assigned a provisional label of Misleading with 43.9% model confidence..."
    },
    "evidence": {
      "status": "contradicting",
      "summary": "External evidence from authoritative sources conflicts with or refutes the claim...",
      "sources": [
        {
          "relation": "contradicts",
          "relevance_score": 0.57,
          "snippet": "investigation into vaccines and autism spectrum disorder has shown that there is no relationship...",
          "source": "Wikipedia",
          "title": "Vaccines and autism",
          "url": "https://en.wikipedia.org/wiki/Vaccines_and_autism"
        }
      ]
    },
    "verification": {
      "assessment_note": "Both the classifier's pattern recognition and external authoritative records...",
      "conflict_detected": false,
      "is_low_confidence": true,
      "result": "Potentially False -- retrieved evidence contradicts the claim, but model confidence is low.",
      "status": "LIKELY_FALSE"
    },
    "responsible_ai": {
      "confidence_note": "Model confidence is not factual certainty.",
      "verification_note": "Evidence retrieval is separate from the classifier prediction. When evidence is insufficient, the claim remains unverified."
    }
  }
}
```

---

## 4. AI Service Integration
- Clean, thin `app.py` architecture: Business logic is decoupled from route handlers.
- `app.py` delegates directly to `verify_claim(text)` in `services/verification.py`, which seamlessly orchestrates:
  - `services/claim_extractor.py` (claim normalization & query formulation)
  - `services/explainer.py` (DistilBERT inference & Integrated Gradients attribution)
  - `services/evidence.py` (Wikipedia API search, relevance scoring & stance detection)
  - `services/report_generator.py` (human-readable formatting)

---

## 5. Model Loading Strategy
- **Global Singleton (`get_explainer()`)**: The DistilBERT model weights and tokenizer are loaded into memory once and reused across subsequent requests.
- **CPU Practicality**: Eliminates redundant disk I/O and weight instantiation overhead, ensuring rapid subsequent requests (~0.3–0.6s total turnaround on CPU).

---

## 6. Input Validation
Implemented in `utils/validators.py` via `validate_input_text()`:
- Enforces string type and non-null values.
- Strips leading and trailing whitespace.
- Rejects empty, whitespace-only, or single-character inputs.
- Minimum length constraint: 5 characters / at least 2 words.
- Maximum safe length constraint: 10,000 characters (returns `HTTP 413` in API).
- Returns user-friendly validation error messages without leaking stack traces.

---

## 7. External Evidence Failure Handling
- External network requests to Wikipedia Search API are wrapped with defensive error handling and request timeouts.
- If an external timeout or connectivity drop occurs, the pipeline **does not crash**:
  - The classifier prediction and token attributions complete normally.
  - Evidence status is safely marked as `insufficient`.
  - The assessment status defaults to `UNVERIFIED`.
  - Zero fabricated fallback URLs or mock citations are injected.

---

## 8. Error Handling
- Custom Flask error handlers for `404 Not Found` and `500 Server Error`.
- When requesting `/api/*` routes, error handlers return structured JSON payloads (`{"success": false, "error": "..."}`) rather than HTML tracebacks.
- Python internal stack traces are suppressed from client responses and logged safely via standard Python `logging`.

---

## 9. Security Checks
- **No Secrets Exposed**: API keys, database credentials, and file paths are excluded from API responses and health checks.
- **Template Safety**: Jinja2 auto-escaping is active across all HTML templates to prevent cross-site scripting (XSS).
- **No User-Controlled File Paths**: No user input touches file system paths or dynamic imports.
- **Configuration Defaults**: `DEBUG` is set to `False` in production configuration; secrets are loaded through `.env` with `.env.example` template provided.

---

## 10 & 11. Test Execution & Results

Executed via Python's standard `unittest` test runner:
`python -m unittest discover -s truthlens-ai/tests -p "test_*.py"`

| Test Module | Test Case | Description | Result |
|---|---|---|---|
| `test_app.py` | `test_home_route` | Verifies `GET /` renders index.html | **PASS** |
| `test_app.py` | `test_get_analyze_route` | Verifies `GET /analyze` renders input form | **PASS** |
| `test_app.py` | `test_post_analyze_empty_input` | Rejects empty input with HTTP 400 | **PASS** |
| `test_app.py` | `test_post_analyze_too_short` | Rejects inputs < 5 chars with HTTP 400 | **PASS** |
| `test_app.py` | `test_post_analyze_too_long` | Rejects inputs > 10,000 chars with HTTP 400 | **PASS** |
| `test_app.py` | `test_post_analyze_and_redirect` | Valid claim redirects to `/result/<id>` | **PASS** |
| `test_app.py` | `test_view_result_not_found` | Invalid analysis ID returns HTTP 404 | **PASS** |
| `test_app.py` | `test_evidence_failure_graceful_handling` | Network exception gracefully degrades to insufficient | **PASS** |
| `test_api.py` | `test_api_health` | Verifies `GET /api/health` returns status without leaks | **PASS** |
| `test_api.py` | `test_api_analyze_missing_json_header` | Rejects non-JSON requests with HTTP 400 | **PASS** |
| `test_api.py` | `test_api_analyze_missing_text_field` | Rejects missing 'text' key with HTTP 400 | **PASS** |
| `test_api.py` | `test_api_analyze_empty_text` | Rejects empty text with HTTP 400 | **PASS** |
| `test_api.py` | `test_api_analyze_too_short` | Rejects text < 5 chars with HTTP 400 | **PASS** |
| `test_api.py` | `test_api_analyze_exceeds_max_length` | Returns HTTP 413 for text > 10,000 chars | **PASS** |
| `test_api.py` | `test_api_analyze_valid_claim` | End-to-end integration test with production model | **PASS** |
| `test_api.py` | `test_api_analyze_external_evidence_failure` | External timeout yields HTTP 200 with insufficient status | **PASS** |

**Summary: 16 Tests Ran in 6.61s &mdash; 16 PASSED, 0 FAILED.**

---

## 12. Known Limitations
1. **CPU Inference Latency**:
   On CPU hardware, forward inference and 5-step Integrated Gradients take approximately 0.4–0.7 seconds per claim. For production scale, batch asynchronous workers (e.g. Celery / Redis) or GPU acceleration would be recommended.
2. **Synchronous Evidence Retrieval**:
   External HTTP calls to Wikipedia are synchronous during request processing; connection timeouts are capped at 6 seconds to prevent worker thread starvation.
