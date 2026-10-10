"""tests/test_phase13_realtime.py
Comprehensive test suite for Phase 13 Real-Time Intelligence & Live Verification features.
Tests SSRF security, News URL verification, Live Evidence refresh, Real Dashboard statistics,
and API endpoints.
"""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from database import db, Analysis, format_relative_time
from services.url_extractor import (
    validate_and_resolve_url,
    is_safe_ip,
    fetch_and_extract_article,
    SimpleHTMLArticleExtractor
)
from services.evidence import search_evidence


class TestPhase13Realtime(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ==============================================================
    # 1. SSRF & URL VALIDATION TESTS
    # ==============================================================

    def test_ssrf_blocks_localhost_and_loopback(self):
        """SSRF protection blocks localhost, 127.0.0.1, and 0.0.0.0."""
        blocked_urls = [
            "http://localhost/admin",
            "http://127.0.0.1:8000/secret",
            "http://0.0.0.0:5000",
            "http://[::1]/status",
            "http://metadata.google.internal/computeMetadata/v1/"
        ]
        for url in blocked_urls:
            is_valid, normalized, err = validate_and_resolve_url(url)
            self.assertFalse(is_valid, f"Expected {url} to be blocked by SSRF defense.")
            self.assertIn("prohibited", err.lower())

    def test_ssrf_blocks_private_ip_ranges(self):
        """SSRF protection blocks RFC 1918 private IPs and cloud metadata."""
        private_ips = [
            "10.0.0.1",
            "192.168.1.1",
            "172.16.0.5",
            "169.254.169.254",
            "127.0.0.1"
        ]
        for ip in private_ips:
            self.assertFalse(is_safe_ip(ip), f"Expected IP {ip} to be unsafe.")

    def test_ssrf_blocks_disallowed_schemes(self):
        """Only http and https schemes are permitted; file://, ftp:// are rejected."""
        invalid_schemes = [
            "file:///etc/passwd",
            "ftp://ftp.example.com/file.txt",
            "javascript:alert(1)",
            "gopher://example.com"
        ]
        for url in invalid_schemes:
            is_valid, _, err = validate_and_resolve_url(url)
            self.assertFalse(is_valid)
            self.assertIn("http", (err or "").lower())

    # ==============================================================
    # 2. ARTICLE HTML EXTRACTION TESTS
    # ==============================================================

    def test_html_article_parser(self):
        """HTML extractor cleanly extracts title and article paragraphs while stripping scripts."""
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Breaking: Major Climate Accord Signed - Reuters</title>
          <meta property="og:title" content="Major Climate Accord Signed">
        </head>
        <body>
          <nav><a href="/">Home</a></nav>
          <article>
            <h1>Major Climate Accord Signed</h1>
            <p>Delegates from over 190 nations reached a landmark consensus today in Geneva.</p>
            <p>The treaty establishes legally binding targets for industrial emission reductions.</p>
          </article>
          <script>console.log("tracking code");</script>
          <footer>Copyright 2026</footer>
        </body>
        </html>
        """
        parser = SimpleHTMLArticleExtractor()
        parser.feed(sample_html)
        self.assertEqual(parser.og_title, "Major Climate Accord Signed")
        self.assertTrue(len(parser.paragraphs) >= 2)
        combined = " ".join(parser.paragraphs)
        self.assertIn("190 nations", combined)
        self.assertNotIn("tracking code", combined)

    # ==============================================================
    # 3. NEWS URL ANALYSIS PIPELINE & API TESTS
    # ==============================================================

    @patch("app.fetch_and_extract_article")
    def test_analyze_url_web_form(self, mock_fetch):
        """POST /analyze with mode='url' successfully extracts content and runs verification."""
        mock_fetch.return_value = {
            "success": True,
            "url": "https://example-news.org/article-1",
            "title": "Global Leaders Meet on Health Initiatives",
            "content": "World leaders convened today to discuss childhood vaccine distribution and public health.",
            "word_count": 14,
            "error": None
        }

        response = self.client.post("/analyze", data={
            "mode": "url",
            "url": "https://example-news.org/article-1"
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        # Verify Analysis was persisted in database with URL metadata
        record = Analysis.query.first()
        self.assertIsNotNone(record)
        self.assertEqual(record.source_url, "https://example-news.org/article-1")
        self.assertEqual(record.article_title, "Global Leaders Meet on Health Initiatives")
        self.assertIn(record.predicted_label, ["Reliable", "Misleading", "False"])

    def test_api_analyze_url_missing_body(self):
        """POST /api/analyze-url without JSON returns 400."""
        response = self.client.post("/api/analyze-url", data="invalid")
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])

    def test_api_analyze_url_ssrf_rejection(self):
        """POST /api/analyze-url with localhost URL returns 400 with SSRF block message."""
        response = self.client.post("/api/analyze-url", json={"url": "http://127.0.0.1:8080/api"})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("prohibited", data["error"].lower())

    @patch("app.fetch_and_extract_article")
    def test_api_analyze_url_success(self, mock_fetch):
        """POST /api/analyze-url with valid URL returns 200 with full analysis payload."""
        mock_fetch.return_value = {
            "success": True,
            "url": "https://reputable-news.com/tech-breakthrough",
            "title": "New Clean Energy Technology Verified",
            "content": "Researchers at the national lab demonstrated a solar cell achieving 40 percent efficiency under standard conditions.",
            "word_count": 18,
            "error": None
        }

        response = self.client.post("/api/analyze-url", json={"url": "https://reputable-news.com/tech-breakthrough"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertIn("analysis_id", data)
        self.assertEqual(data["article_title"], "New Clean Energy Technology Verified")
        self.assertEqual(data["source_url"], "https://reputable-news.com/tech-breakthrough")
        self.assertIn("prediction", data["analysis"])

    # ==============================================================
    # 4. REAL DASHBOARD STATISTICS & TELEMETRY TESTS
    # ==============================================================

    def test_dashboard_empty_state(self):
        """GET /dashboard and /api/dashboard with empty database return real zero counts."""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No analyses yet.", response.data)

        api_res = self.client.get("/api/dashboard")
        self.assertEqual(api_res.status_code, 200)
        metrics = api_res.get_json()["metrics"]
        self.assertEqual(metrics["total_count"], 0)
        self.assertEqual(metrics["reliable_count"], 0)
        self.assertEqual(metrics["misleading_count"], 0)
        self.assertEqual(metrics["false_count"], 0)
        self.assertEqual(metrics["conflict_count"], 0)
        self.assertEqual(metrics["recent_analyses"], [])

    def test_dashboard_real_statistics_calculation(self):
        """Dashboard calculates exact counts and metrics from SQLite records."""
        # Insert known test records
        rec1 = Analysis(
            input_text="George Washington was the first president.",
            predicted_label="Reliable",
            confidence=0.95,
            verification_status="SUPPORTED",
            evidence_status="supporting",
            class_probabilities={"Reliable": 0.95, "Misleading": 0.03, "False": 0.02},
            conflict_detected=False
        )
        rec2 = Analysis(
            input_text="Vaccines cause autism claim refuted.",
            predicted_label="False",
            confidence=0.90,
            verification_status="LIKELY_FALSE",
            evidence_status="contradicting",
            class_probabilities={"Reliable": 0.05, "Misleading": 0.05, "False": 0.90},
            conflict_detected=False
        )
        rec3 = Analysis(
            input_text="A sensational but true historical event.",
            predicted_label="Misleading",
            confidence=0.85,
            verification_status="CONFLICTING_SIGNALS",
            evidence_status="supporting",
            class_probabilities={"Reliable": 0.10, "Misleading": 0.85, "False": 0.05},
            conflict_detected=True
        )
        db.session.add_all([rec1, rec2, rec3])
        db.session.commit()

        api_res = self.client.get("/api/dashboard")
        self.assertEqual(api_res.status_code, 200)
        metrics = api_res.get_json()["metrics"]

        self.assertEqual(metrics["total_count"], 3)
        self.assertEqual(metrics["reliable_count"], 1)
        self.assertEqual(metrics["false_count"], 1)
        self.assertEqual(metrics["misleading_count"], 1)
        self.assertEqual(metrics["conflict_count"], 1)
        self.assertEqual(metrics["today_count"], 3)
        self.assertAlmostEqual(metrics["average_confidence"], 0.90, places=2)
        self.assertEqual(len(metrics["recent_analyses"]), 3)

    # ==============================================================
    # 5. LIVE EVIDENCE REFRESH & TIMESTAMPS TESTS
    # ==============================================================

    def test_evidence_freshness_timestamps(self):
        """search_evidence returns real ISO and display timestamps."""
        result = search_evidence("Water freezes at zero degrees Celsius.")
        self.assertIn("retrieved_at", result)
        self.assertIn("retrieved_at_display", result)
        self.assertIn("status", result)
        # Check ISO timestamp parseable
        dt = datetime.fromisoformat(result["retrieved_at"])
        self.assertIsNotNone(dt)

    def test_relative_time_formatter(self):
        """format_relative_time produces accurate human-readable strings."""
        now = datetime.now(timezone.utc)
        self.assertEqual(format_relative_time(now), "Just now")
        self.assertEqual(format_relative_time(now - timedelta(seconds=35)), "35 seconds ago")
        self.assertEqual(format_relative_time(now - timedelta(minutes=5)), "5 minutes ago")
        self.assertEqual(format_relative_time(now - timedelta(hours=3)), "3 hours ago")
        self.assertEqual(format_relative_time(now - timedelta(days=2)), "2 days ago")

    @patch("services.evidence.WikipediaEvidenceProvider.search")
    def test_evidence_refresh_endpoint(self, mock_wiki_search):
        """POST /api/refresh-evidence/<id> re-queries evidence without modifying model prediction."""
        # Setup initial record
        record = Analysis(
            input_text="George Washington was the first President of the United States.",
            predicted_label="Reliable",
            confidence=0.92,
            verification_status="SUPPORTED",
            evidence_status="supporting",
            class_probabilities={"Reliable": 0.92, "Misleading": 0.04, "False": 0.04},
            evidence_sources=[]
        )
        db.session.add(record)
        db.session.commit()
        original_id = record.id

        # Mock fresh live evidence return
        mock_wiki_search.return_value = [{
            "title": "George Washington",
            "url": "https://en.wikipedia.org/wiki/George_Washington",
            "source": "Wikipedia",
            "snippet": "George Washington was the first President of the United States, serving from 1789 to 1797."
        }]

        # Call refresh API
        response = self.client.post(f"/api/refresh-evidence/{original_id}")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])

        # Verify in DB: Model prediction is strictly UNCHANGED
        updated = db.session.get(Analysis, original_id)
        self.assertEqual(updated.predicted_label, "Reliable")
        self.assertEqual(updated.confidence, 0.92)
        self.assertEqual(updated.evidence_status, "supporting")
        self.assertTrue(len(updated.evidence_sources) > 0)


if __name__ == "__main__":
    unittest.main()
