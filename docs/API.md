# TruthLens AI — API & Endpoint Documentation

This document describes all web routes and REST API endpoints available in the **TruthLens AI** application.

---

## 1. Overview & Base URL

- **Local Base URL**: `http://127.0.0.1:5000`
- **Content Type**: `application/json` for REST API endpoints; `text/html` for Web UI routes.

---

## 2. REST API Endpoints

### 2.1 Health Check
- **Endpoint**: `GET /api/health`
- **Description**: Returns system operational status, active model configuration, and evidence provider availability.
- **Request Parameters**: None
- **Response Headers**: `Content-Type: application/json`
- **Response Status**: `200 OK`

#### Example Response
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

---

### 2.2 Analyze Claim
- **Endpoint**: `POST /api/analyze`
- **Description**: Submits claim text to the complete AI verification pipeline (claim extraction, transformer inference, Integrated Gradients explainability, evidence retrieval, dual-signal synthesis) and records results in the SQLite database.
- **Request Headers**:
  - `Content-Type: application/json`
- **Request Body Schema**:
```json
{
  "text": "string (Required, 5 to 10,000 characters)"
}
```

#### Request Validation & Error Responses:
- **400 Bad Request**: Non-JSON request body or input under 5 characters.
  ```json
  {
    "success": false,
    "error": "Input text must be at least 5 characters long."
  }
  ```
- **413 Payload Too Large**: Input exceeding 10,000 characters.
  ```json
  {
    "success": false,
    "error": "Input text exceeds maximum allowed length of 10000 characters."
  }
  ```
- **500 Internal Server Error**: Unexpected processing failure during analysis.
  ```json
  {
    "success": false,
    "error": "An internal error occurred during claim verification. Please try again."
  }
  ```

#### Example Success Response (`200 OK`):
```json
{
  "success": true,
  "analysis_id": 42,
  "analysis": {
    "claim": "Drinking lemon water cures all forms of cancer.",
    "original_text": "Drinking lemon water cures all forms of cancer.",
    "search_query": "Drinking lemon water cures all forms of cancer",
    "prediction": {
      "label": "False",
      "confidence": 0.8421
    },
    "probabilities": {
      "False": 0.8421,
      "Misleading": 0.1132,
      "Reliable": 0.0447
    },
    "explanation": {
      "summary": "Model identified key patterns in the text.",
      "confidence_status": "Model prediction",
      "important_phrases": [
        {
          "phrase": "cures all forms of cancer",
          "importance": 0.452,
          "direction": "supports_prediction"
        }
      ]
    },
    "evidence": {
      "status": "contradicting",
      "summary": "External evidence from authoritative sources conflicts with or refutes the claim.",
      "sources": [
        {
          "title": "Alternative cancer treatments",
          "url": "https://en.wikipedia.org/wiki/Alternative_cancer_treatments",
          "source": "Wikipedia",
          "relation": "contradicts",
          "relevance_score": 0.88,
          "snippet": "Scientific consensus indicates unproven remedies do not cure cancer."
        }
      ]
    },
    "verification": {
      "status": "LIKELY_FALSE",
      "result": "Likely False -- retrieved evidence contradicts the claim.",
      "conflict_detected": false,
      "assessment_note": "Both classifier pattern recognition and external authoritative records indicate this assertion is false.",
      "is_low_confidence": false
    },
    "responsible_ai": {
      "confidence_note": "Model confidence is not factual certainty.",
      "verification_note": "Evidence retrieval is separate from the classifier prediction. When evidence is insufficient, the claim remains unverified."
    }
  }
}
```

---

## 3. Web UI Routes

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Renders the landing page with platform overview, key metrics, and call-to-action buttons. |
| `GET` | `/analyze` | Displays the interactive claim submission form with character count and quick sample selectors. |
| `POST` | `/analyze` | Form POST endpoint for claim submissions. On validation success, verifies claim, saves to database, and redirects (`302`) to `/result/<id>`. On validation error, returns `400` with the rendered form. |
| `GET` | `/result/<analysis_id>` | Renders the detailed verification report for a given numeric analysis ID. Returns `404` if the ID is missing or invalid. |
| `GET` | `/history` | Displays the searchable history table of all prior analyses stored in SQLite in reverse chronological order. |
| `GET` | `/history/<analysis_id>` | Consistent detail route displaying the full analysis report for a past run. |
| `GET` | `/about` | Displays the platform architecture, model comparison disclosures, and Responsible AI guidelines. |

---

## 4. Error Handling & Status Codes

- **`400 Bad Request`**: Malformed JSON or input validation failure.
- **`404 Not Found`**: Missing web page or nonexistent analysis record ID. JSON returned when hitting `/api/*`, HTML page rendered for web browser requests.
- **`413 Payload Too Large`**: Input text exceeds 10,000 characters.
- **`500 Internal Server Error`**: Unhandled exception during pipeline execution. Database transaction rolls back cleanly.
