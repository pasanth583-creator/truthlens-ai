"""Google Fact Check Tools API Service for TruthLens AI.

Provides secure, robust integration with the official Google Fact Check Tools API
(ClaimReview API endpoint).
"""

import os
import re
import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path

# Load environment configuration if not already loaded
from config import Config

logger = logging.getLogger("truthlens.google_fact_check")

GOOGLE_FACT_CHECK_ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


def get_api_key() -> Optional[str]:
    """Retrieve Google Fact Check API key securely from environment."""
    key = (
        os.environ.get("GOOGLE_FACT_CHECK_API_KEY")
        or os.environ.get("GOOGLE_FACTCHECK_API_KEY")
        or getattr(Config, "GOOGLE_FACT_CHECK_API_KEY", "")
    )
    if key and key.strip():
        return key.strip()
    return None


def is_configured() -> bool:
    """Return True if a valid Google Fact Check API key is configured."""
    return get_api_key() is not None


def classify_rating(textual_rating: str) -> str:
    """Map human textual rating from fact checker into standardized TruthLens categories.
    
    Categories:
        - TRUE
        - FALSE
        - MISLEADING
        - PARTLY TRUE
        - UNVERIFIED
        - NO EXISTING FACT CHECK
    """
    if not textual_rating or not textual_rating.strip():
        return "UNVERIFIED"

    rating_clean = textual_rating.strip().lower()

    # 1. Partly true / mixed indicators (Check first to catch "Mostly False", "Partly False", etc.)
    partly_true_patterns = [
        r"\bmostly false\b", r"\bpartly false\b", r"\bpartially false\b",
        r"\bpartly true\b", r"\bhalf true\b", r"\bpartially true\b",
        r"\bmostly true\b", r"\bmixture\b", r"\bsomewhat true\b",
        r"\bbarely true\b", r"\bcompromise\b", r"\bhalf-truth\b"
    ]
    for pat in partly_true_patterns:
        if re.search(pat, rating_clean):
            return "PARTLY TRUE"

    # 2. Misleading indicators
    misleading_patterns = [
        r"\bmisleading\b", r"\bmisattributed\b", r"\baltered\b",
        r"\bout of context\b", r"\bcontext\b", r"\bdistorted\b",
        r"\bexaggerated\b", r"\bmanipulated\b", r"\bmissing context\b",
        r"\bdeceptive\b", r"\bunsubstantiated\b"
    ]
    for pat in misleading_patterns:
        if re.search(pat, rating_clean):
            return "MISLEADING"

    # 3. Direct / common false indicators
    false_patterns = [
        r"\bfalse\b", r"\bfake\b", r"\bincorrect\b", r"\bpants on fire\b",
        r"\bfabricated\b", r"\bdebunked\b", r"\brefuted\b", r"\binaccurate\b",
        r"\bhoax\b", r"\bunproven\b", r"\bscam\b", r"\bwrong\b", r"\bmyth\b",
        r"\bfalse claim\b", r"\bnot true\b", r"\bno evidence\b"
    ]
    for pat in false_patterns:
        if re.search(pat, rating_clean):
            return "FALSE"

    # 4. Direct / common true indicators
    true_patterns = [
        r"\btrue\b", r"\bcorrect\b", r"\baccurate\b",
        r"\bverified\b", r"\bsupported\b", r"\bconfirmed\b"
    ]
    for pat in true_patterns:
        if re.search(pat, rating_clean):
            return "TRUE"

    return "UNVERIFIED"


def search_fact_checks(
    query: str,
    page_size: int = 10,
    language_code: str = "en"
) -> Dict[str, Any]:
    """Search Google Fact Check Tools API for verified ClaimReviews.
    
    Args:
        query: Search query or factual claim text.
        page_size: Maximum number of results to retrieve (default 10).
        language_code: Target language code (default 'en').
        
    Returns:
        Structured dictionary containing status, error details (if any), and parsed results.
    """
    now_dt = datetime.now(timezone.utc)
    iso_timestamp = now_dt.isoformat()
    display_timestamp = now_dt.strftime("%d %b %Y, %H:%M UTC")

    if not query or not query.strip():
        return {
            "status": "error",
            "error_code": "EMPTY_QUERY",
            "status_code": "EMPTY_QUERY",
            "status_display": "ERROR — EMPTY QUERY",
            "message": "Search query cannot be empty.",
            "results": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }

    api_key = get_api_key()
    if not api_key:
        logger.info("Google Fact Check API key is not configured in the environment.")
        return {
            "status": "error",
            "error_code": "MISSING_API_KEY",
            "status_code": "UNAVAILABLE",
            "status_display": "UNAVAILABLE — NOT CONFIGURED",
            "message": "Google Fact Check API key is not configured in the environment.",
            "results": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }

    encoded_query = urllib.parse.quote(query.strip())
    endpoint_url = (
        f"{GOOGLE_FACT_CHECK_ENDPOINT}"
        f"?query={encoded_query}&pageSize={min(max(page_size, 1), 10)}"
        f"&languageCode={urllib.parse.quote(language_code)}"
        f"&key={api_key}"
    )

    headers = {
        "User-Agent": "TruthLensAI-FactChecker/1.0",
        "Accept": "application/json"
    }

    req = urllib.request.Request(endpoint_url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            status_code = response.status
            if status_code != 200:
                logger.warning("Google Fact Check API returned non-200 HTTP status: %d", status_code)
                return {
                    "status": "error",
                    "error_code": f"HTTP_{status_code}",
                    "status_code": f"HTTP_{status_code}",
                    "status_display": f"ERROR — HTTP {status_code}",
                    "message": f"Google Fact Check API returned HTTP status {status_code}.",
                    "results": [],
                    "retrieved_at": iso_timestamp,
                    "retrieved_at_display": display_timestamp
                }
            raw_bytes = response.read()
            try:
                raw_data = json.loads(raw_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as json_err:
                logger.warning("Failed to decode Google Fact Check API JSON response: %s", str(json_err))
                return {
                    "status": "error",
                    "error_code": "MALFORMED_RESPONSE",
                    "status_code": "MALFORMED_RESPONSE",
                    "status_display": "ERROR — MALFORMED RESPONSE",
                    "message": "Malformed JSON response received from Google Fact Check API.",
                    "results": [],
                    "retrieved_at": iso_timestamp,
                    "retrieved_at_display": display_timestamp
                }
    except urllib.error.HTTPError as http_err:
        code = http_err.code
        logger.warning("Google Fact Check API HTTP Error: %d - %s", code, http_err.reason)
        if code in (401, 403):
            return {
                "status": "error",
                "error_code": "API_RESTRICTED_OR_NOT_ENABLED",
                "status_code": "API_RESTRICTED_OR_NOT_ENABLED",
                "status_display": f"ERROR — API RESTRICTED / NOT ENABLED (HTTP {code})",
                "message": "Google Fact Check API key is invalid, restricted, or Fact Check Tools API is not enabled in Google Cloud Console.",
                "results": [],
                "retrieved_at": iso_timestamp,
                "retrieved_at_display": display_timestamp
            }
        elif code == 400:
            return {
                "status": "error",
                "error_code": "INVALID_QUERY",
                "status_code": "INVALID_QUERY",
                "status_display": "ERROR — INVALID QUERY (HTTP 400)",
                "message": "Invalid query parameters provided to Google Fact Check API.",
                "results": [],
                "retrieved_at": iso_timestamp,
                "retrieved_at_display": display_timestamp
            }
        elif code == 429:
            return {
                "status": "error",
                "error_code": "RATE_LIMITED",
                "status_code": "RATE_LIMITED",
                "status_display": "ERROR — RATE LIMIT EXCEEDED (HTTP 429)",
                "message": "Google Fact Check API quota or rate limit exceeded.",
                "results": [],
                "retrieved_at": iso_timestamp,
                "retrieved_at_display": display_timestamp
            }
        elif 500 <= code <= 599:
            return {
                "status": "error",
                "error_code": f"SERVER_ERROR_{code}",
                "status_code": f"SERVER_ERROR_{code}",
                "status_display": f"ERROR — SERVER ERROR (HTTP {code})",
                "message": f"Google Fact Check API server error (HTTP {code}).",
                "results": [],
                "retrieved_at": iso_timestamp,
                "retrieved_at_display": display_timestamp
            }
        else:
            return {
                "status": "error",
                "error_code": f"HTTP_{code}",
                "status_code": f"HTTP_{code}",
                "status_display": f"ERROR — HTTP {code}",
                "message": f"Google Fact Check API returned HTTP error {code}.",
                "results": [],
                "retrieved_at": iso_timestamp,
                "retrieved_at_display": display_timestamp
            }
    except urllib.error.URLError as url_err:
        logger.warning("Google Fact Check API network connection failed: %s", str(url_err.reason))
        return {
            "status": "error",
            "error_code": "NETWORK_ERROR",
            "status_code": "NETWORK_ERROR",
            "status_display": "ERROR — NETWORK CONNECTION FAILED",
            "message": "Unable to reach Google Fact Check API due to a network connectivity error.",
            "results": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }
    except (TimeoutError, OSError) as time_err:
        logger.warning("Google Fact Check API request timed out: %s", str(time_err))
        return {
            "status": "error",
            "error_code": "TIMEOUT",
            "status_code": "TIMEOUT",
            "status_display": "ERROR — REQUEST TIMEOUT",
            "message": "Google Fact Check API request timed out.",
            "results": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }
    except Exception as exc:
        logger.warning("Unexpected error during Google Fact Check retrieval: %s", type(exc).__name__)
        return {
            "status": "error",
            "error_code": "UNKNOWN_ERROR",
            "status_code": "UNKNOWN_ERROR",
            "status_display": "ERROR — UNEXPECTED EXCEPTION",
            "message": "An unexpected error occurred while communicating with Google Fact Check API.",
            "results": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }

    raw_claims = raw_data.get("claims", [])
    if not raw_claims:
        return {
            "status": "no_existing_fact_check",
            "status_code": "LIVE_NO_MATCH",
            "status_display": "LIVE — REQUEST SUCCESSFUL, NO MATCHING RESULTS",
            "message": "No existing fact-check found in Google Fact Check database.",
            "results": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }

    parsed_results: List[Dict[str, Any]] = []
    for c in raw_claims:
        claim_text = c.get("text", query.strip())
        claimant = c.get("claimant", "Unknown Claimant")
        claim_date = c.get("claimDate", "")
        reviews = c.get("claimReview", [])

        for r in reviews:
            publisher_obj = r.get("publisher", {})
            publisher_name = publisher_obj.get("name", "Fact Checker")
            publisher_site = publisher_obj.get("site", "")
            review_url = r.get("url", "")
            review_title = r.get("title", claim_text)
            review_date = r.get("reviewDate", "")
            textual_rating = r.get("textualRating", "Unrated")
            verdict = classify_rating(textual_rating)

            parsed_results.append({
                "claim": claim_text,
                "claimant": claimant,
                "claim_date": claim_date,
                "publisher": publisher_name,
                "publisher_url": publisher_site,
                "fact_check_title": review_title,
                "fact_check_url": review_url,
                "review_date": review_date,
                "rating": textual_rating,
                "verdict": verdict,
                "retrieved_at": iso_timestamp,
                "retrieved_at_display": display_timestamp
            })

    if not parsed_results:
        return {
            "status": "no_existing_fact_check",
            "status_code": "LIVE_NO_MATCH",
            "status_display": "LIVE — REQUEST SUCCESSFUL, NO MATCHING RESULTS",
            "message": "No reviews found for matching claims.",
            "results": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }

    return {
        "status": "success",
        "status_code": "LIVE_FOUND",
        "status_display": "LIVE — REQUEST SUCCESSFUL, RESULTS FOUND",
        "message": f"Found {len(parsed_results)} matching fact-check records.",
        "results": parsed_results,
        "retrieved_at": iso_timestamp,
        "retrieved_at_display": display_timestamp
    }


def fact_check_article_claims(text: str) -> Dict[str, Any]:
    """Extract individual factual claims from an article and search Google Fact Check for each."""
    from services.claim_extractor import extract_claims_from_text, extract_claim

    now_dt = datetime.now(timezone.utc)
    iso_timestamp = now_dt.isoformat()
    display_timestamp = now_dt.strftime("%d %b %Y, %H:%M UTC")

    if not is_configured():
        return {
            "status": "success",
            "provider_status": "UNAVAILABLE",
            "status_display": "UNAVAILABLE — NOT CONFIGURED",
            "message": "Google Fact Check API key is not configured in the environment.",
            "total_claims": 0,
            "matched_claims": 0,
            "claims": [],
            "queries_used": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }

    if not text or not text.strip():
        return {
            "status": "error",
            "error_code": "EMPTY_QUERY",
            "provider_status": "EMPTY_QUERY",
            "status_display": "ERROR — EMPTY INPUT",
            "message": "Input text cannot be empty.",
            "total_claims": 0,
            "matched_claims": 0,
            "claims": [],
            "queries_used": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp
        }

    cleaned_text = text.strip()
    extracted_claims = extract_claims_from_text(cleaned_text, max_claims=4)

    if not extracted_claims:
        single = extract_claim(cleaned_text)
        if isinstance(single, dict) and single.get("claim"):
            extracted_claims = [{"claim": single["claim"]}]
        else:
            extracted_claims = [{"claim": cleaned_text[:200]}]

    unique_claims: List[str] = []
    seen = set()
    for c in extracted_claims:
        if isinstance(c, dict):
            c_text = c.get("claim", "")
        else:
            c_text = str(c)
        c_clean = c_text.strip()
        if c_clean and c_clean.lower() not in seen:
            seen.add(c_clean.lower())
            unique_claims.append(c_clean)

    claims_output: List[Dict[str, Any]] = []
    matched_count = 0
    queries_used: List[str] = []
    provider_errors: List[str] = []
    successful_requests = 0

    for claim_item in unique_claims[:4]:
        queries_used.append(claim_item)
        api_res = search_fact_checks(claim_item, page_size=5)
        status = api_res.get("status", "error")
        results = api_res.get("results", [])

        if status == "success" and results:
            successful_requests += 1
            matched_count += 1
            top_result = results[0]
            claims_output.append({
                "claim": claim_item,
                "status": "LIVE — MATCH FOUND",
                "verdict": top_result.get("verdict", "UNVERIFIED"),
                "rating": top_result.get("rating", "Unrated"),
                "publisher": top_result.get("publisher", "Unknown Publisher"),
                "review_date": top_result.get("review_date", ""),
                "source_url": top_result.get("fact_check_url", ""),
                "claimant": top_result.get("claimant", ""),
                "results": results
            })
        elif status == "no_existing_fact_check" or (status == "success" and not results):
            successful_requests += 1
            claims_output.append({
                "claim": claim_item,
                "status": "LIVE — NO MATCHING FACT-CHECK",
                "verdict": "NO EXISTING FACT CHECK",
                "rating": "No existing fact-check found",
                "publisher": "Google Fact Check Tools",
                "review_date": "",
                "source_url": "",
                "claimant": "",
                "results": [],
                "note": "Google Fact Check Tools did not find an existing fact-check for this claim."
            })
        else:
            err_msg = api_res.get("message", "API Request Failed")
            err_display = api_res.get("status_display", "ERROR — REQUEST FAILED")
            provider_errors.append(err_display)
            claims_output.append({
                "claim": claim_item,
                "status": err_display,
                "verdict": "UNVERIFIED",
                "rating": err_msg,
                "publisher": "Google Fact Check Tools",
                "review_date": "",
                "source_url": "",
                "claimant": "",
                "results": []
            })

    if matched_count > 0:
        provider_status = "LIVE_FOUND"
        status_display = "LIVE — REQUEST SUCCESSFUL, RESULTS FOUND"
        summary_msg = f"Retrieved {matched_count} matching fact-check records from accredited organizations."
    elif successful_requests > 0:
        provider_status = "LIVE_NO_MATCH"
        status_display = "LIVE — REQUEST SUCCESSFUL, NO MATCHING RESULTS"
        summary_msg = "Google Fact Check Tools request succeeded, but no existing fact-check records matched the claim."
    elif provider_errors:
        provider_status = "ERROR"
        status_display = provider_errors[0]
        summary_msg = f"Google Fact Check Tools API request failed: {status_display}"
    else:
        provider_status = "UNAVAILABLE"
        status_display = "UNAVAILABLE — NOT CONFIGURED"
        summary_msg = "Google Fact Check Tools API is not configured."

    return {
        "status": "success",
        "provider_status": provider_status,
        "status_display": status_display,
        "message": summary_msg,
        "total_claims": len(claims_output),
        "matched_claims": matched_count,
        "claims": claims_output,
        "queries_used": queries_used,
        "retrieved_at": iso_timestamp,
        "retrieved_at_display": display_timestamp
    }
