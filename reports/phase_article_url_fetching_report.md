# Comprehensive Verification Report: Article URL Fetching & 401 Root Cause Resolution

**Project:** TruthLens AI — Explainable Fake-News Detection System  
**Workspace:** `C:/Users/A K Pasanth/OneDrive/Documents/Fake News Detection System/truthlens-ai`  
**Phase:** Urgent Bug Fix — Article URL Fetching & Verification Pipeline  
**Date:** October 9, 2026  
**Test Suite Status:** 89/89 Tests Passing (`OK`)  

---

## 1. Root Cause Analysis (Task 1)

### 1.1 Origin of the "Article server responded with HTTP status 401" Error
1. **Publisher-Side Bot Block (Target Website):** When testing against major news publishers (e.g., `https://www.reuters.com/world/`), the target publisher origin servers return `HTTP 401 Unauthorized` / `HTTP 403 Forbidden` to automated clients when requests are recognized as non-browser scrapers or when section indices are queried.
2. **Stale Process In Memory:** The long-running terminal process running on port 5000 had older code in memory that printed the unformatted message string `Article server responded with HTTP status 401.` without user-friendly guidance or fallback actions.
3. **Google Fact Check API Separation:** Google Fact Check API returns `403 Forbidden` when the Fact Check Tools API is not enabled on the developer's Google Cloud project, but is fully insulated and caught with `API_RESTRICTED_OR_NOT_ENABLED`, cleanly falling back to Wikipedia evidence retrieval without failing the user request.

---

## 2. Technical Architecture & Fix Details (Task 2 & 3)

### 2.1 Multi-Layer Network Retrieval & SSRF Defense
- **SSRF Validation:** Pre-flight domain resolution via `socket.getaddrinfo`, blocking localhost (`127.0.0.1`, `0.0.0.0`), private RFC 1918 subnets, link-local (`169.254.x`), and cloud metadata (`169.254.169.254`, `metadata.google.internal`).
- **Browser-Emulated Session:** Using `requests.Session` with modern browser headers (`Mozilla/5.0 Chrome/124.0.0.0`, `Sec-Ch-Ua`, `Sec-Fetch-*`, `Accept-Language`) and automatic content decompression.
- **Recursive Redirect Re-validation:** Every HTTP 3xx redirect target IP is verified against SSRF rules before following the next hop.

### 2.2 Cascading Content Extraction
1. **Trafilatura:** Primary extractor for high-precision removal of navigation, cookie notices, and ads.
2. **BeautifulSoup4:** Secondary DOM-aware parser targeting semantic `<article>`, `[itemprop="articleBody"]`, and `<main>`.
3. **SimpleHTMLArticleExtractor:** Zero-dependency fallback parser.

### 2.3 Transparent Diagnostic Categorization & Text Fallback
- `401`: `AUTH_REQUIRED` — Explains that the publisher requires subscription login.
- `403`: `FORBIDDEN_OR_PAYWALL` — Explains access was restricted or paywalled.
- `429`: `RATE_LIMITED` — Explains rate limit was exceeded.
- `HOMEPAGE_SECTION_DETECTED` — Explains that the URL is a category or homepage rather than a single article.
- **Interactive Fallback:** The UI provides an immediate **"Paste Article Text Instead"** button that activates the Claim Statement tab with the textarea focused and previous context retained.

---

## 3. Detailed Verification Test Results (Task 4)

| Test Case | Input Type | Actual HTTP Status | Article Extraction Result | Pipeline Ran? | Model Prediction | Evidence Verdict | Test Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Accessible Public Article** | News URL (`en.wikipedia.org/wiki/Climate_change`) | 200 OK | Success (28,323 words, Title: *Climate change - Wikipedia*) | Yes | Reliable (99.8%) | Supported | **PASS** |
| **2. Section / Homepage** | News URL (`reuters.com/world/`) | 401 Unauthorized (Publisher origin) | Handled: Informative `HOMEPAGE_SECTION_DETECTED` notice + fallback | Prompted | N/A (Extraction stopped safely) | N/A | **PASS** |
| **3. Paywalled / 401 Target** | News URL (Mock 401 Auth) | 401 Unauthorized | Handled: `AUTH_REQUIRED` diagnostic notice + fallback paste button | Prompted | N/A (Protected page) | N/A | **PASS** |
| **4. Forbidden / 403 Target** | News URL (`apnews.com` / Mock 403) | 403 Forbidden | Handled: `FORBIDDEN_OR_PAYWALL` notice + fallback paste button | Prompted | N/A (WAF protected) | N/A | **PASS** |
| **5. Invalid URL Scheme / Host** | News URL (`localhost:5000` / `ftp://...`) | N/A (Blocked pre-flight) | Blocked by SSRF filter (`RESTRICTED_URL`) | No | N/A (Security defense) | N/A | **PASS** |
| **6. Manually Pasted Text** | Pasted Claim Text | N/A (Local POST) | Full text processed directly without re-fetching publisher page | Yes | Reliable (99.4%) | Supported | **PASS** |
| **7. Claim with No Fact-Check Match** | Custom Claim | 200 OK | Text processed -> Fact Check 0 matches -> Wikipedia fallback | Yes | Reliable (98.9%) | Unverified / Supported | **PASS** |

---

## 4. Automated Test Suite (Task 5)

Ran complete test suite across all 7 test files:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

**Results:**
- **Ran:** 89 tests
- **Passed:** 89 tests
- **Failed:** 0
- **Errors:** 0
- **Status:** `OK`

---

## 5. Modified Files Summary

- [services/url_extractor.py](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/services/url_extractor.py) — Hardened network fetching layer via `requests.Session`, recursive SSRF redirect re-validation, Trafilatura + BS4 cascade, and structured error categorization.
- [requirements.txt](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/requirements.txt) — Added `trafilatura>=2.0.0` and `beautifulsoup4>=4.12.0`.
- [app.py](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/app.py) — Enriched `/analyze` and `/api/analyze-url` endpoints with structured diagnostics and fallback handling.
- [templates/analyze.html](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/templates/analyze.html) — Added interactive "Paste Article Text Instead" fallback button and enhanced 7-stage loading overlay.
- [static/js/analyze.js](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/static/js/analyze.js) — Added fallback paste action listener and dynamic stage progression.
- [tests/test_article_fetcher.py](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/tests/test_article_fetcher.py) — Dedicated unit tests for SSRF security, 401/403/429 status handling, Trafilatura/BS4 extraction, and API endpoints.
- [reports/phase_article_url_fetching_report.md](file:///C:/Users/A%20K%20Pasanth/OneDrive/Documents/Fake%20News%20Detection%20System/truthlens-ai/reports/phase_article_url_fetching_report.md) — Documentation and audit report.
