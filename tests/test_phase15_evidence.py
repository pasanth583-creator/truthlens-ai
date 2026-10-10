import os
import json
import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from database import db, Analysis
from services.claim_extractor import extract_claim, extract_claims_from_text, generate_search_queries
from services.evidence import (
    WikipediaEvidenceProvider,
    GoogleFactCheckProvider,
    search_evidence,
    calculate_relevance,
    determine_relation
)
from services.verification import synthesize_verification, verify_claim
from services.google_fact_check import search_fact_checks, fact_check_article_claims, classify_rating


class TestPhase15EvidenceAndVerification(unittest.TestCase):
    """Automated test suite validating all Phase 15 evidence retrieval & verification requirements."""

    def setUp(self):
        self.app = create_app("testing")
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # 1. Wikipedia Search Result Parsing
    def test_wikipedia_search_result_parsing(self):
        """Test MediaWiki API response parsing including title, URL, clean snippet, pageid, and timestamp."""
        provider = WikipediaEvidenceProvider()
        mock_response_data = {
            "query": {
                "search": [
                    {
                        "title": "Water on Mars",
                        "pageid": 123456,
                        "snippet": "<span>Signs of <b>Water on Mars</b></span> discovered by NASA rovers."
                    }
                ]
            }
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = provider.search("Water on Mars", max_results=5)
            self.assertEqual(len(results), 1)
            item = results[0]
            self.assertEqual(item["title"], "Water on Mars")
            self.assertEqual(item["page_id"], 123456)
            self.assertEqual(item["url"], "https://en.wikipedia.org/wiki/Water_on_Mars")
            self.assertEqual(item["snippet"], "Signs of Water on Mars discovered by NASA rovers.")
            self.assertIn("retrieved_at", item)

    # 2. Wikipedia Fallback & Deduplication
    def test_wikipedia_search_fallback_and_deduplication(self):
        """Test fallback across multiple queries and deduplication of records."""
        provider = WikipediaEvidenceProvider()
        queries = ["NASA Mars water", "Water on Mars", "Perseverance rover"]
        
        mock_item_1 = {"title": "Water on Mars", "pageid": 1, "snippet": "Water on Mars is ice."}
        mock_item_2 = {"title": "Perseverance", "pageid": 2, "snippet": "Perseverance landed."}

        with patch.object(provider, "search", side_effect=[
            [{"title": "Water on Mars", "url": "https://en.wikipedia.org/wiki/Water_on_Mars", "snippet": "Ice."}],
            [{"title": "Water on Mars", "url": "https://en.wikipedia.org/wiki/Water_on_Mars", "snippet": "Ice."}],
            [{"title": "Perseverance", "url": "https://en.wikipedia.org/wiki/Perseverance", "snippet": "Rover."}]
        ]):
            sources, code, display = provider.search_with_fallback(queries, max_results=5)
            self.assertEqual(len(sources), 2)
            self.assertEqual(code, "LIVE_FOUND")
            self.assertIn("LIVE", display)

    # 3. Google ClaimReview Response Parsing
    def test_google_claimreview_parsing(self):
        """Test Google Fact Check Tools ClaimReview response parsing."""
        mock_google_response = {
            "claims": [
                {
                    "text": "Vaccines cause autism",
                    "claimant": "Social Media Posts",
                    "claimDate": "2024-01-01",
                    "claimReview": [
                        {
                            "publisher": {"name": "PolitiFact", "site": "politifact.com"},
                            "url": "https://www.politifact.com/factchecks/autism-vaccines",
                            "title": "Claim about vaccines and autism debunked",
                            "reviewDate": "2024-01-02",
                            "textualRating": "Pants on Fire"
                        }
                    ]
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_google_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("services.google_fact_check.get_api_key", return_value="AIzaSyTestValidKey"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                res = search_fact_checks("vaccines cause autism")
                self.assertEqual(res["status"], "success")
                self.assertEqual(res["status_code"], "LIVE_FOUND")
                self.assertEqual(len(res["results"]), 1)
                first = res["results"][0]
                self.assertEqual(first["publisher"], "PolitiFact")
                self.assertEqual(first["verdict"], "FALSE")
                self.assertEqual(first["rating"], "Pants on Fire")

    # 4. Google Fact Check Zero Results (Accurate Status)
    def test_google_zero_results_accurate_status(self):
        """Test Google Fact Check successful query with 0 matching claims."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"claims": []}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("services.google_fact_check.get_api_key", return_value="AIzaSyTestValidKey"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                res = search_fact_checks("Zorblax City national holiday")
                self.assertEqual(res["status"], "no_existing_fact_check")
                self.assertEqual(res["status_code"], "LIVE_NO_MATCH")
                self.assertEqual(len(res["results"]), 0)
                self.assertIn("NO MATCHING RESULTS", res["status_display"])

    # 5. Google Fact Check HTTP 403 / 429 / Timeout Errors
    def test_google_fact_check_error_statuses(self):
        """Test Google Fact Check provider returns accurate error codes for 403, 429, and timeouts."""
        import urllib.error
        
        # 403 Forbidden
        with patch("services.google_fact_check.get_api_key", return_value="AIzaSyRestrictedKey"):
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 403, "Forbidden", {}, None)):
                res403 = search_fact_checks("test query")
                self.assertEqual(res403["status"], "error")
                self.assertEqual(res403["error_code"], "API_RESTRICTED_OR_NOT_ENABLED")
                self.assertIn("HTTP 403", res403["status_display"])

        # 429 Rate Limited
        with patch("services.google_fact_check.get_api_key", return_value="AIzaSyQuotaKey"):
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)):
                res429 = search_fact_checks("test query")
                self.assertEqual(res429["status"], "error")
                self.assertEqual(res429["error_code"], "RATE_LIMITED")
                self.assertIn("HTTP 429", res429["status_display"])

        # Timeout
        with patch("services.google_fact_check.get_api_key", return_value="AIzaSyTimeoutKey"):
            with patch("urllib.request.urlopen", side_effect=TimeoutError("Request timed out")):
                res_to = search_fact_checks("test query")
                self.assertEqual(res_to["status"], "error")
                self.assertEqual(res_to["error_code"], "TIMEOUT")
                self.assertIn("TIMEOUT", res_to["status_display"])

    # 6. Multi-claim extraction from long articles
    def test_long_article_claim_extraction(self):
        """Test extracting 2-4 distinct factual claims and queries from an article."""
        article_text = (
            "Explore Mars: NASA's Journey to the Red Planet. "
            "NASA has discovered evidence of water ice in craters on the surface of Mars. "
            "The Perseverance rover has been actively searching for ancient microbial life since 2021. "
            "In 1976, the Viking 1 lander touched down safely on Mars and transmitted the first surface photos. "
            "Scientists continue to study the Martian atmosphere and climate history."
        )
        claims = extract_claims_from_text(article_text, max_claims=4)
        self.assertGreaterEqual(len(claims), 2)
        self.assertLessEqual(len(claims), 4)
        for c in claims:
            self.assertIn("claim", c)
            self.assertIn("queries", c)
            self.assertGreaterEqual(len(c["queries"]), 1)

    # 7. Relevance scoring and stance determination
    def test_relevance_and_stance_scoring(self):
        """Test supporting and contradicting stance determination against known assertions."""
        claim_support = "George Washington was the first President of the United States."
        source_support = {
            "title": "George Washington",
            "snippet": "George Washington was a Founding Father and the first president of the United States.",
            "source": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/George_Washington"
        }
        self.assertGreaterEqual(calculate_relevance(claim_support, source_support), 0.5)
        self.assertEqual(determine_relation(claim_support, source_support), "supports")

        claim_contra = "Earth is the largest planet in the solar system."
        source_contra = {
            "title": "Jupiter",
            "snippet": "Jupiter is the fifth planet from the Sun and the largest in the Solar System.",
            "source": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/Jupiter"
        }
        self.assertEqual(determine_relation(claim_contra, source_contra), "contradicts")

        claim_vaccine = "Vaccines cause autism."
        source_vaccine = {
            "title": "Vaccines and autism",
            "snippet": "Extensive investigation has shown there is no evidence and no relationship between vaccines and autism.",
            "source": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/Vaccines_and_autism"
        }
        self.assertEqual(determine_relation(claim_vaccine, source_vaccine), "contradicts")

    # 8. Separate Model Prediction from Evidence Verdict
    def test_verdict_synthesis_rules(self):
        """Test synthesis logic separates neural confidence from evidence-based verdict."""
        # A. Strong supporting evidence -> SUPPORTED
        s1 = synthesize_verification("Reliable", 0.637, "supporting")
        self.assertEqual(s1["status"], "SUPPORTED")
        self.assertIn("Supported", s1["result"])

        # B. Strong contradicting evidence -> LIKELY_FALSE
        s2 = synthesize_verification("False", 0.85, "contradicting")
        self.assertEqual(s2["status"], "LIKELY_FALSE")
        self.assertIn("Likely False", s2["result"])

        # C. Disagreement -> CONFLICTING_SIGNALS
        s3 = synthesize_verification("Reliable", 0.90, "contradicting")
        self.assertEqual(s3["status"], "CONFLICTING_SIGNALS")
        self.assertTrue(s3["conflict_detected"])

        # D. No meaningful evidence -> UNVERIFIED / INSUFFICIENT EVIDENCE
        s4 = synthesize_verification("Reliable", 0.637, "insufficient")
        self.assertEqual(s4["status"], "UNVERIFIED")
        self.assertIn("Unverified / Insufficient Evidence", s4["result"])

    # 9. Real Refresh Evidence Action
    def test_refresh_evidence_action(self):
        """Test POST /refresh-evidence/<id> performs a fresh retrieval and updates database record."""
        # Create initial record
        record = Analysis(
            input_text="George Washington was the first President of the United States.",
            predicted_label="Reliable",
            confidence=0.88,
            verification_status="UNVERIFIED",
            evidence_status="insufficient",
            class_probabilities={"False": 0.05, "Misleading": 0.07, "Reliable": 0.88},
            evidence_sources=[]
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id

        mock_new_evidence = {
            "evidence_status": "supporting",
            "summary": "Verified by historical archives.",
            "sources": [
                {
                    "title": "George Washington",
                    "source": "Wikipedia",
                    "relation": "supports",
                    "relevance_score": 0.95,
                    "snippet": "First president of the United States.",
                    "url": "https://en.wikipedia.org/wiki/George_Washington"
                }
            ]
        }

        with patch("app.search_evidence", return_value=mock_new_evidence):
            resp = self.client.post(f"/refresh-evidence/{record_id}", follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

            updated = db.session.get(Analysis, record_id)
            self.assertEqual(updated.evidence_status, "supporting")
            self.assertEqual(updated.verification_status, "SUPPORTED")
            self.assertEqual(len(updated.evidence_sources), 1)


if __name__ == "__main__":
    unittest.main()
