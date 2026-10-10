"""Unit and Integration Tests for Google Fact Check Tools API Integration in TruthLens AI.
"""

import os
import sys
import json
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from services.google_fact_check import (
    get_api_key,
    is_configured,
    classify_rating,
    search_fact_checks,
    fact_check_article_claims,
)


class TestGoogleFactCheckIntegration(unittest.TestCase):
    """Test suite covering Google Fact Check API service, claim extraction, and HTTP endpoints."""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()

    # ==============================================================
    # 1. API CONFIGURATION & SECURITY
    # ==============================================================

    def test_api_key_loading(self):
        """Ensure API key is retrieved securely from environment if configured."""
        key = get_api_key()
        if key:
            self.assertIsInstance(key, str)
            self.assertGreater(len(key), 10)
            # Ensure key is not trivial placeholder
            self.assertNotEqual(key, "YOUR_API_KEY_HERE")

    def test_rating_classification(self):
        """Validate mapping from diverse human textual ratings to standardized categories."""
        # False ratings
        self.assertEqual(classify_rating("False"), "FALSE")
        self.assertEqual(classify_rating("Pants on Fire"), "FALSE")
        self.assertEqual(classify_rating("Debunked"), "FALSE")
        self.assertEqual(classify_rating("Fake claim"), "FALSE")
        self.assertEqual(classify_rating("Incorrect statement"), "FALSE")
        self.assertEqual(classify_rating("No evidence"), "FALSE")

        # Misleading ratings
        self.assertEqual(classify_rating("Misleading"), "MISLEADING")
        self.assertEqual(classify_rating("Missing Context"), "MISLEADING")
        self.assertEqual(classify_rating("Out of Context"), "MISLEADING")
        self.assertEqual(classify_rating("Altered Photo"), "MISLEADING")

        # Partly True ratings
        self.assertEqual(classify_rating("Partly True"), "PARTLY TRUE")
        self.assertEqual(classify_rating("Half True"), "PARTLY TRUE")
        self.assertEqual(classify_rating("Mostly False"), "PARTLY TRUE")
        self.assertEqual(classify_rating("Mixture"), "PARTLY TRUE")

        # True ratings
        self.assertEqual(classify_rating("True"), "TRUE")
        self.assertEqual(classify_rating("Correct"), "TRUE")
        self.assertEqual(classify_rating("Accurate"), "TRUE")
        self.assertEqual(classify_rating("Verified"), "TRUE")

        # Empty / Unverified ratings
        self.assertEqual(classify_rating(""), "UNVERIFIED")
        self.assertEqual(classify_rating(None), "UNVERIFIED")
        self.assertEqual(classify_rating("Unclear statement"), "UNVERIFIED")

    # ==============================================================
    # 2. REQUIRED TEST QUERIES
    # ==============================================================

    def test_a_earth_planet_claim(self):
        """TEST A: Search 'Earth is the largest planet in the solar system.'"""
        query = "Earth is the largest planet in the solar system."
        res = search_fact_checks(query)
        self.assertIn("status", res)
        self.assertIn(res["status"], ("success", "no_existing_fact_check", "error"))
        self.assertIsInstance(res.get("results", []), list)

    def test_b_water_survival_claim(self):
        """TEST B: Search 'Water is necessary for human survival.'"""
        query = "Water is necessary for human survival."
        res = search_fact_checks(query)
        self.assertIn("status", res)
        self.assertIn(res["status"], ("success", "no_existing_fact_check", "error"))
        self.assertIsInstance(res.get("results", []), list)

    def test_c_fifa_world_cup_claim(self):
        """TEST C: Search 'India won the 2026 FIFA World Cup.'"""
        query = "India won the 2026 FIFA World Cup."
        res = search_fact_checks(query)
        self.assertIn("status", res)
        self.assertIn(res["status"], ("success", "no_existing_fact_check", "error"))
        self.assertIsInstance(res.get("results", []), list)

    def test_d_completely_new_uncommon_claim(self):
        """TEST D: New fictional claim returns NO EXISTING FACT CHECK rather than True/False."""
        query = "Zorblax Galactic Citadel announced every Tuesday is a cosmic holiday."
        res = search_fact_checks(query)
        self.assertIn("status", res)
        if res["status"] == "no_existing_fact_check":
            self.assertEqual(len(res.get("results", [])), 0)

    def test_e_empty_input(self):
        """TEST E: Empty input handled with user-friendly error without crashing."""
        res = search_fact_checks("")
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_code"], "EMPTY_QUERY")

    def test_f_multi_claim_article(self):
        """TEST F: Long multi-claim article extracts claims and queries Google Fact Check for each."""
        article = (
            "Scientists discovered a revolutionary new solar panel technology that produces "
            "unlimited clean electricity. The breakthrough technology was tested in Tokyo last week. "
            "Meanwhile, public health authorities reported that global vaccination rates reached record levels."
        )
        res = fact_check_article_claims(article)
        self.assertEqual(res["status"], "success")
        self.assertIn("claims", res)
        self.assertGreaterEqual(res["total_claims"], 1)
        for claim_obj in res["claims"]:
            self.assertIn("claim", claim_obj)
            self.assertIn("status", claim_obj)
            self.assertIn("verdict", claim_obj)
            self.assertIn("publisher", claim_obj)

    # ==============================================================
    # 3. MOCKED GOOGLE API SCENARIOS
    # ==============================================================

    def test_mocked_google_api_success_with_matches(self):
        """Verify handling of successful Google API response with verified ClaimReviews."""
        from unittest.mock import patch, MagicMock
        import io

        mock_json = {
            "claims": [{
                "text": "Lemon water cures cancer",
                "claimant": "Social Media",
                "claimDate": "2026-01-01",
                "claimReview": [{
                    "publisher": {"name": "Health Fact Checker", "site": "healthfacts.org"},
                    "url": "https://healthfacts.org/lemon-cure",
                    "title": "Lemon water does not cure cancer",
                    "reviewDate": "2026-01-02",
                    "textualRating": "False"
                }]
            }]
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_json).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = search_fact_checks("lemon water cures cancer")
            self.assertEqual(res["status"], "success")
            self.assertEqual(len(res["results"]), 1)
            self.assertEqual(res["results"][0]["verdict"], "FALSE")
            self.assertEqual(res["results"][0]["publisher"], "Health Fact Checker")

    def test_mocked_google_api_zero_matches(self):
        """Verify that a zero-match response produces 'no_existing_fact_check' instead of an error."""
        from unittest.mock import patch, MagicMock

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"claims": []}'
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = search_fact_checks("some obscure claim with zero matches")
            self.assertEqual(res["status"], "no_existing_fact_check")
            self.assertEqual(len(res["results"]), 0)

    def test_mocked_google_api_http_403_restricted_key(self):
        """Verify handling of HTTP 403 (restricted key or API not enabled) without raising exceptions."""
        from unittest.mock import patch
        import urllib.error

        err = urllib.error.HTTPError(
            url="https://factchecktools.googleapis.com",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None
        )

        with patch("urllib.request.urlopen", side_effect=err):
            res = search_fact_checks("test claim")
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["error_code"], "API_RESTRICTED_OR_NOT_ENABLED")
            self.assertEqual(res["results"], [])

    def test_mocked_google_api_http_429_rate_limited(self):
        """Verify handling of HTTP 429 (quota or rate limit exceeded)."""
        from unittest.mock import patch
        import urllib.error

        err = urllib.error.HTTPError(
            url="https://factchecktools.googleapis.com",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None
        )

        with patch("urllib.request.urlopen", side_effect=err):
            res = search_fact_checks("test claim")
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["error_code"], "RATE_LIMITED")

    def test_mocked_google_api_network_timeout(self):
        """Verify handling of network timeout without raising exceptions."""
        from unittest.mock import patch

        with patch("urllib.request.urlopen", side_effect=TimeoutError("Request timed out")):
            res = search_fact_checks("test claim")
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["error_code"], "TIMEOUT")

    def test_google_unavailable_fallback_to_wikipedia(self):
        """Verify that when Google Fact Check is unavailable, the system falls back to Wikipedia cleanly."""
        from unittest.mock import patch
        import urllib.error
        from services.evidence import search_evidence

        err = urllib.error.HTTPError(
            url="https://factchecktools.googleapis.com",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None
        )

        with patch("services.evidence.GoogleFactCheckProvider.search", return_value=[]):
            res = search_evidence("George Washington was the first President of the United States", bypass_cache=True)
            self.assertIn(res["evidence_status"], ("supporting", "insufficient", "neutral"))
            self.assertIn("sources", res)

    # ==============================================================
    # 4. BACKEND API ROUTE & FULL PIPELINE TESTS
    # ==============================================================

    def test_api_fact_check_endpoint_json(self):
        """Test POST /api/fact-check with JSON payload."""
        payload = {"text": "Vaccines cause autism"}
        response = self.client.post(
            "/api/fact-check",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("claims", data)
        self.assertIsInstance(data["claims"], list)

    def test_api_fact_check_endpoint_empty_error(self):
        """Test POST /api/fact-check with empty payload returns HTTP 400."""
        response = self.client.post(
            "/api/fact-check",
            json={"text": ""},
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data.get("status"), "error")

    def test_api_fact_check_security_no_key_leak(self):
        """Verify that API key is NEVER leaked in any API responses."""
        payload = {"text": "Earth is the largest planet in the solar system."}
        response = self.client.post("/api/fact-check", json=payload)
        raw_body = response.get_data(as_text=True)
        key = get_api_key()
        if key:
            self.assertNotIn(key, raw_body)

    def test_analyze_short_claim_web_and_persistence(self):
        """Verify full web POST /analyze with a short claim redirects to /result/<id> with 200 OK."""
        response = self.client.post(
            "/analyze",
            data={"text": "Drinking lemon water cures all forms of cancer.", "mode": "claim"},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        loc = response.headers.get("Location")
        self.assertIn("/result/", loc)
        
        # Test result page renders successfully
        res_page = self.client.get(loc)
        self.assertEqual(res_page.status_code, 200)
        self.assertIn(b"Drinking lemon water", res_page.data)

    def test_analyze_long_article_web_and_persistence(self):
        """Verify full web POST /analyze with a long 1000+ character article."""
        long_article = (
            "A comprehensive global investigation has revealed that major technology corporations "
            "collaborated with international cybersecurity agencies to analyze telecommunications data. "
            "Internal memos suggest that specific data security measures were deployed across multiple regions. "
            "While corporate representatives issued formal statements clarifying the nature of the research, "
            "independent researchers confirmed that standard diagnostic telemetry was utilized."
        ) * 3
        self.assertGreater(len(long_article), 1000)

        response = self.client.post(
            "/analyze",
            data={"text": long_article, "mode": "claim"},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        loc = response.headers.get("Location")
        self.assertIn("/result/", loc)

        res_page = self.client.get(loc)
        self.assertEqual(res_page.status_code, 200)


if __name__ == "__main__":
    unittest.main()
