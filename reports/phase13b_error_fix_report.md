# Phase 13B — Error Resolution & Live Evidence Verification Report

**Project:** TruthLens AI — Explainable Fake-News Detection System  
**Date:** October 9, 2026  
**Status:** **RESOLVED & FULLY VERIFIED**  
**Test Suite:** 79/79 Unit & Integration Tests Passed  

---

## 1. Executive Summary

During Phase 13 testing, submitting claims on the `/analyze` web form resulted in:
> *“Validation Notice: An unexpected internal error occurred while analyzing the claim. Please try again.”*

Following a comprehensive step-by-step diagnostic audit, the underlying root cause was identified, isolated, and resolved. All 79 automated unit and integration tests are passing, genuine external API requests have been verified, and end-to-end browser QA has confirmed smooth claim verification, result rendering, and database persistence.

---

## 2. Root Cause Analysis

Tracing the request lifecycle revealed three distinct issues:

1. **Database Path Resolution on Windows (`(sqlite3.OperationalError) unable to open database file`)**:
   - In `.env`, `DATABASE_URL` was configured as a relative URI (`sqlite:///database/truthlens.db`).
   - In `config.py`, this relative path was parsed without anchoring it to the project's absolute base directory (`BASE_DIR`).
   - When the Flask backend processed a claim and attempted `db.session.commit()`, SQLite failed to open the database file whenever the working directory differed or when Windows backslashes conflicted with URI syntax.
   - The transaction failed and threw an internal `OperationalError`, causing the analyze route to catch the exception and return a 500 error page.

2. **Misleading Error Presentation in the UI**:
   - In `templates/analyze.html`, the error banner was hardcoded to display `<strong>Validation Notice:</strong> {{ error }}` for all errors, causing backend 500 exceptions to be mislabeled as client validation errors.

3. **Google Fact Check API Key Restrictions & HTTP Error Handling**:
   - Genuine test requests against the Google Fact Check Tools API (`https://factchecktools.googleapis.com/v1alpha1/claims:search`) returned HTTP 403 Forbidden because the configured API key had domain/IP restrictions or the Fact Check Tools API was not enabled on the associated Google Cloud project.
   - The error handling in `services/google_fact_check.py` and `services/evidence.py` needed refined error categorization (differentiating 401/403 restricted keys, 429 rate limits, timeouts, and zero-result responses) to ensure seamless fallback to the Wikipedia evidence provider without raising unhandled exceptions.

---

## 3. Files Modified

| File | Changes Made |
|---|---|
| [config.py](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/config.py) | Implemented robust cross-platform path resolution for `SQLALCHEMY_DATABASE_URI` ensuring absolute POSIX-compliant paths (`f"sqlite:///{_db_path}"`); added fallback support for both `GOOGLE_FACT_CHECK_API_KEY` and `GOOGLE_FACTCHECK_API_KEY` environment variables. |
| [services/google_fact_check.py](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/services/google_fact_check.py) | Refined HTTP status code handling (400, 401/403, 429, 5xx), added JSON decode error protection (`MALFORMED_RESPONSE`), and ensured API key is never exposed in logs or outputs. |
| [services/evidence.py](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/services/evidence.py) | Streamlined request headers and added robust error handling for `GoogleFactCheckProvider`, ensuring automatic, seamless fallback to the `WikipediaEvidenceProvider`. |
| [app.py](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/app.py) | Enabled `exc_info=True` in error loggers to record full tracebacks securely in backend logs while returning safe user messages with `error_type="server_error"`. |
| [templates/analyze.html](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/templates/analyze.html) | Updated alert heading to conditionally render `System Notice:` for internal errors versus `Validation Notice:` for input validation errors. |
| [tests/test_google_fact_check.py](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/tests/test_google_fact_check.py) | Added comprehensive test cases for mocked 200 matches, zero-match responses, HTTP 403, HTTP 429, network timeouts, Wikipedia provider fallback, and full pipeline persistence. |

---

## 4. Google API Request & Provider Status

### Genuine Request Audit (Local Environment)
- **Endpoint**: `https://factchecktools.googleapis.com/v1alpha1/claims:search`
- **Authentication**: Key loaded securely from environment (presence confirmed, value never logged).
- **HTTP Status Received**: `403 Forbidden` (`API_RESTRICTED_OR_NOT_ENABLED`).
- **Graceful Degradation**: System logged warning securely without crashing, handled zero claims safely, and successfully utilized the `Wikipedia (Public API)` provider for live evidence retrieval.

### Multi-Provider Redundancy
1. **Primary Provider (Google Fact Check Tools API)**:
   - When configured and valid: Extracts ClaimReviews, publishers, review dates, and textual ratings.
   - When unconfigured or returning 403/429/timeout: Safely returns empty results without throwing exceptions.
2. **Fallback Provider (Wikipedia MediaWiki Public API)**:
   - Actively queries encyclopedic summaries, computes keyword/authority relevance scores, and classifies stance (`supports`, `contradicts`, `neutral`).

---

## 5. Automated Test Suite Results

```text
Ran 79 tests in 81.465s

OK
```

### Breakdown of Passing Tests:
- `tests/test_api.py`: 12/12 passed (health check, JSON API input validation, probability structure, security headers).
- `tests/test_app.py`: 13/13 passed (web UI routes, claim submissions, URL mode, history views, error handlers).
- `tests/test_database.py`: 10/10 passed (schema integrity, relative time formatting, JSON serialization).
- `tests/test_google_fact_check.py`: 19/19 passed (rating classification, mocked 200, zero matches, 403, 429, timeout, fallback).
- `tests/test_phase13_realtime.py`: 15/15 passed (real-time telemetry, relative timestamps, evidence refresh).
- `tests/test_phase13a_evidence_first.py`: 10/10 passed (evidence-first decision matrix, conflict resolution).

---

## 6. End-to-End Browser QA Results

End-to-end verification was performed using the automated browser subagent on `http://127.0.0.1:5000`:

1. **Submission**:
   - Submitted test claim: *"Drinking lemon water cures all forms of cancer."*
   - Submission processed via live progress overlay and redirected to `/result/20`.
2. **Result View (`/result/20`)**:
   - **Verdict Banner**: Correctly rendered `Final Verification Assessment: Unverified / Insufficient Evidence`.
   - **Model Prediction**: Displayed DistilBERT output (`False`, 36.0% confidence) with full probability breakdown.
   - **Explainability**: Integrated Gradients highlighted influential tokens (*"all"*, *"water"*, *"cures"*, *"lemon"*).
   - **Evidence Verification**: Displayed 3 authoritative Wikipedia records (*Lemon water*, *Limonene*, *Barbara O'Neill*).
   - **Signal Comparison Matrix**: Rendered dual-signal alignment comparison.
3. **History Verification (`/history`)**:
   - Analysis Record #20 confirmed in the SQLite history table with full timestamps and verdict badges.

---

## 7. Remaining Limitations & Recommendations

1. **Google Cloud Console API Key Configuration**:
   - To activate live Google Fact Check results, the API key in `.env` must have the **Fact Check Tools API** enabled in the Google Cloud Console, and any HTTP referrer or IP restrictions must include the host environment.
2. **Wikipedia Rate-Limiting**:
   - The Wikipedia provider enforces a polite 0.2s minimum request interval and in-memory TTL caching (1 hour) to ensure reliable upstream access.
