# TruthLens AI — Phase 15 Live Evidence Retrieval and Google Fact Check Verification Report

**Date:** October 10, 2026  
**Project:** TruthLens AI — Explainable Fake-News Detection System  
**Workspace:** `C:/Users/A K Pasanth/OneDrive/Documents/Fake News Detection System/truthlens-ai`

---

## 1. Executive Summary & Root Cause Analysis

### Identified Root Causes:
1. **Wikipedia Zero Records on Long Articles / URLs (`https://science.nasa.gov/mars/`):**
   - **Diagnosis:** When a user submitted an article or URL, the extraction pipeline sent the full 7,000+ character body text into `calculate_relevance()` against 200-character Wikipedia search snippets. The word-set intersection ratio computed against a 600+ word document was diluted below `0.02`, triggering the `relevance < 0.30` threshold and discarding all retrieved records as irrelevant.
   - **Resolution:** Upgraded `services/claim_extractor.py` and `services/evidence.py` to extract 2–4 concise, declarative factual sub-claims from long articles. Each sub-claim generates 2–4 targeted search queries, queries the MediaWiki API, and scores retrieved snippets against its specific sub-claim rather than the entire 10,000-character document.
2. **Google Fact Check "LIVE" Status Misreporting:**
   - **Diagnosis:** `templates/result.html` previously reported the provider as `LIVE API` whenever `is_configured` was True, even when real API calls returned HTTP 403 Forbidden (restricted key or Fact Check Tools API not enabled in Google Cloud Console).
   - **Resolution:** Standardized provider state reporting across `services/google_fact_check.py`, `services/verification.py`, and `templates/result.html`. The UI now transparently reports:
     - `LIVE — REQUEST SUCCESSFUL, RESULTS FOUND`
     - `LIVE — REQUEST SUCCESSFUL, NO MATCHING RESULTS`
     - `ERROR — API RESTRICTED / NOT ENABLED (HTTP 403)`
     - `UNAVAILABLE — NOT CONFIGURED`
3. **Evidence Refresh Mechanism:**
   - Added a real backend POST endpoint `/refresh-evidence/<int:analysis_id>` that executes a live re-query against external providers, updates evidence associations in SQLite without destroying history, and refreshes the result view with real retrieval timestamps.

---

## 2. Files Changed & Architectural Enhancements

| File | Changes Made |
| :--- | :--- |
| [`services/claim_extractor.py`](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/services/claim_extractor.py) | • Enhanced `generate_search_queries` with noun-predicate entity extraction and fallback queries.<br>• Enhanced `extract_claims_from_text` to score declarative sentences, filter navigation boilerplate, and extract 2–4 top distinct factual claims.<br>• Updated `extract_claim` to handle long multi-paragraph articles. |
| [`services/evidence.py`](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/services/evidence.py) | • Refactored `WikipediaEvidenceProvider` to use official MediaWiki search API (`action=query&list=search&srsearch=...`).<br>• Implemented query simplification retries and result deduplication.<br>• Fixed relevance calculation to avoid text-length dilution.<br>• Added preference for decisive evidence (`supports`/`contradicts`) over neutral boilerplate in `search_evidence`. |
| [`services/google_fact_check.py`](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/services/google_fact_check.py) | • Standardized provider status reporting (`LIVE_FOUND`, `LIVE_NO_MATCH`, `UNAVAILABLE`, `ERROR`).<br>• Accurate HTTP error code mapping (`API_RESTRICTED_OR_NOT_ENABLED` on 403, `RATE_LIMITED` on 429, `TIMEOUT`).<br>• Prevented classification of claims as false simply on 0 fact-check matches. |
| [`services/verification.py`](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/services/verification.py) | • Multi-claim evidence search with full provider diagnostics.<br>• Enhanced `synthesize_verification` adhering strictly to Phase 15 veracity rules (DistilBERT prediction separated from evidence stance). |
| [`database.py`](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/database.py) | • Dynamic calculation of stance tallies (`supporting_count`, `contradicting_count`, `neutral_count`), provider metadata, and search queries in `Analysis.to_dict()`. |
| [`app.py`](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/app.py) | • Registered typed integer and string routes for `/refresh-evidence/<int:analysis_id>`. |
| [`templates/result.html`](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/templates/result.html) | • Display independent provider statuses, search queries used, stance breakdowns, and working POST `/refresh-evidence/{{ analysis.id }}` form. |
| [`tests/test_phase15_evidence.py`](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/tests/test_phase15_evidence.py) | • Dedicated test suite covering MediaWiki search parsing, Google ClaimReview parsing, HTTP error mapping, fallback queries, and claim decomposition. |

---

## 3. Actual Provider Endpoints & Integration Details

### A. MediaWiki Search API
- **Endpoint:** `https://en.wikipedia.org/w/api.php`
- **Parameters:** `action=query`, `list=search`, `srsearch=<query>`, `format=json`, `srlimit=5`, `utf8=1`
- **Headers:** Descriptive `User-Agent: TruthLensAI-Verification/2.0 (research@truthlens.ai)`
- **Parsed Fields:** `title`, `snippet`, `pageid`, `url` (`https://en.wikipedia.org/?curid=<pageid>`), and UTC retrieval timestamp.

### B. Google Fact Check Tools API
- **Endpoint:** `https://factchecktools.googleapis.com/v1alpha1/claims:search`
- **Parameters:** `query=<claim>`, `key=<SECRET_API_KEY>`, `languageCode=en`, `pageSize=5`
- **Headers/Body:** Standard JSON REST.
- **Parsed Fields:** `claimReviewed`, `claimant`, `claimDate`, `claimReview` (`publisher.name`, `publisher.site`, `url`, `title`, `reviewDate`, `textualRating`).
- **Security:** API key strictly read from `.env` on backend; never exposed to frontend, logs, or API responses.

---

## 4. Test Matrix on Mandatory Evaluation Claims

| Test Case | Input Type | Extracted Claims & Queries | Provider Status | Results Retrieved | Verdict & Stance |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **George Washington** | Statement | *George Washington was the first President of the United States*<br>Query: `"George Washington first President United States"` | Wikipedia: `LIVE_FOUND`<br>Google: `HTTP 403` | 5 records (e.g. *George Washington*, *President of the United States*) | **SUPPORTED**<br>Model: Reliable (57.1%)<br>Evidence: 5 supporting, 0 contradicting |
| **Earth Largest Planet** | Statement | *Earth is the largest planet in the solar system*<br>Query: `"Earth largest planet in the solar system"` | Wikipedia: `LIVE_FOUND`<br>Google: `HTTP 403` | 5 records (e.g. *Earth*, *Planet*, *Jupiter*) | **LIKELY FALSE**<br>Model: Misleading (48.7%)<br>Evidence: Contradicting (Jupiter is largest) |
| **Vaccines & Autism** | Statement | *Vaccines cause autism*<br>Query: `"Vaccines cause autism"` | Wikipedia: `LIVE_FOUND`<br>Google: `HTTP 403` | 5 records (e.g. *MMR vaccine and autism*, *Lancet MMR fraud*) | **LIKELY FALSE**<br>Model: Misleading (58.3%)<br>Evidence: Contradicting |
| **NASA Water on Mars** | Statement | *NASA has discovered evidence of water on Mars*<br>Query: `"NASA discovered evidence water Mars"` | Wikipedia: `LIVE_FOUND`<br>Google: `HTTP 403` | 4 records (e.g. *Water on Mars*, *Mars Reconnaissance Orbiter*) | **SUPPORTED**<br>Model: Reliable (42.8%)<br>Evidence: Supporting |
| **NASA Mars Landing Page** | URL (`https://science.nasa.gov/mars/`) | Extracted Sub-claims: *NASA Mars Exploration*, *Mars missions robotic exploration* | Wikipedia: `LIVE_FOUND`<br>Google: `HTTP 403` | 4 records (e.g. *Mars landing*, *MAVEN*, *Viking 1*) | **SUPPORTED** / Reference Context<br>Model: Reliable (52.6%) |
| **Invented Claim** | Statement | *Zorblax City officially declared every Tuesday a national holiday.* | Wikipedia: `LIVE_NO_MATCH`<br>Google: `HTTP 403` | 0 records | **UNVERIFIED / INSUFFICIENT EVIDENCE**<br>Model: Misleading (47.0%)<br>Hallucination Prevention: 0 fake sources |

---

## 5. Automated Test Suite Results

```text
======================================================================
Ran 112 tests in 63.985s

OK
======================================================================
```
- **Total Unit & Integration Tests:** 112 passed across all test suites.
- **Dedicated Phase 15 Tests (`test_phase15_evidence.py`):** 9/9 passed.
  - `test_wikipedia_search_parsing_success`
  - `test_wikipedia_search_query_fallback`
  - `test_google_claimreview_parsing_success`
  - `test_google_fact_check_zero_results`
  - `test_google_fact_check_http_403_and_429_errors`
  - `test_google_fact_check_timeout_error`
  - `test_claim_extraction_from_long_articles`
  - `test_search_query_generation_distinctness`
  - `test_verdict_synthesis_decision_rules`

---

## 6. End-to-End Browser QA Verification

- **Live URL:** `http://127.0.0.1:5000`
- **Workflows Verified:**
  1. **Claim Statement Input:** Verified analysis, attribution badges, and live evidence rendering.
  2. **News Article URL Input:** Verified real-time URL fetching, declarative claim extraction, and targeted evidence query matching.
  3. **Refresh Evidence Action:** Successfully triggered live re-query via `POST /refresh-evidence/<id>`, updated timestamps, and persisted changes.
  4. **Invented Claim:** Verified zero fabricated records and clean `Unverified / Insufficient Evidence` verdict.
  5. **History & Dashboard:** Verified real-time SQLite persistence (`truthlens.db`) and aggregate metric updates.

---

## 7. Remaining Limitations & Recommendations

1. **Google Fact Check Cloud API Key:**
   - The configured API key in `.env` currently returns HTTP 403 Forbidden from Google Cloud endpoints because the *Fact Check Tools API* service is either not enabled in the user's GCP Project or has IP/referrer restrictions. The application cleanly detects and displays `ERROR — API RESTRICTED / NOT ENABLED (HTTP 403)` without crashing or mislabeling the request. To enable live Google fact-checks, enable the API in Google Cloud Console.
2. **Future Primary Source Expansion:**
   - Modular public reference sources (e.g. PubMed API, arXiv API, Crossref API) can be plugged into `services/evidence.py` following the established `WikipediaEvidenceProvider` interface without altering core inference or schema.
