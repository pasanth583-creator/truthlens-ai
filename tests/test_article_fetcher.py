"""tests/test_article_fetcher.py
Comprehensive test suite for TruthLens AI Real-World Article URL Fetching,
SSRF Defense, Trafilatura/BS4 Content Extraction, and Verification Pipeline Integration.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from database import db
from services.url_extractor import (
    validate_and_resolve_url,
    is_safe_ip,
    is_homepage_or_section,
    fetch_and_extract_article,
    SimpleHTMLArticleExtractor
)


class TestArticleFetcherAndVerification(unittest.TestCase):
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
    # 1. SSRF DEFENSE & NETWORK SAFETY
    # ==============================================================

    def test_ssrf_blocks_private_ip_and_metadata(self):
        """Block loopback, private ranges, link-local, and cloud metadata."""
        dangerous_ips = [
            "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1",
            "169.254.169.254", "0.0.0.0", "100.100.100.200"
        ]
        for ip in dangerous_ips:
            self.assertFalse(is_safe_ip(ip), f"IP {ip} should be rejected.")

    def test_ssrf_blocks_internal_hostnames(self):
        """Reject localhost, *.local, *.internal, and metadata endpoints."""
        restricted_urls = [
            "http://localhost:5000/status",
            "http://127.0.0.1/admin",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://app.local/secret",
            "file:///etc/passwd",
            "gopher://example.com"
        ]
        for url in restricted_urls:
            is_valid, _, err = validate_and_resolve_url(url)
            self.assertFalse(is_valid, f"URL {url} must be blocked.")

    # ==============================================================
    # 2. HOMEPAGE AND SECTION DETECTION
    # ==============================================================

    def test_homepage_and_section_detection(self):
        """Detect homepages and section index paths."""
        self.assertTrue(is_homepage_or_section("/"))
        self.assertTrue(is_homepage_or_section(""))
        self.assertTrue(is_homepage_or_section("/world"))
        self.assertTrue(is_homepage_or_section("/world/"))
        self.assertTrue(is_homepage_or_section("/politics"))
        self.assertTrue(is_homepage_or_section("/news/"))
        self.assertFalse(is_homepage_or_section("/world/2026/10/climate-accord-signed-geneva.html"))

    # ==============================================================
    # 3. HTTP STATUS CODE & ERROR HANDLING
    # ==============================================================

    @patch("services.url_extractor._fetch_html_network")
    def test_http_401_authentication_required(self, mock_net):
        """HTTP 401 returns clear authentication error and AUTH_REQUIRED code."""
        mock_net.return_value = (False, None, {
            "success": False,
            "url": "https://news.example.com/premium",
            "canonical_url": "https://news.example.com/premium",
            "domain": "news.example.com",
            "title": "",
            "author": "",
            "publish_date": "",
            "content": "",
            "word_count": 0,
            "error": "The publisher requires subscription authentication or login (HTTP 401). Please paste the article text directly below to verify the claim.",
            "error_code": "AUTH_REQUIRED",
            "is_homepage": False
        })

        with patch("services.url_extractor.validate_and_resolve_url", return_value=(True, "https://news.example.com/premium", None)):
            res = fetch_and_extract_article("https://news.example.com/premium")
            self.assertFalse(res["success"])
            self.assertEqual(res["error_code"], "AUTH_REQUIRED")
            self.assertIn("authentication", res["error"].lower())

    @patch("services.url_extractor._fetch_html_network")
    def test_http_403_forbidden_or_paywall(self, mock_net):
        """HTTP 403 returns clear forbidden/paywall notice."""
        mock_net.return_value = (False, None, {
            "success": False,
            "url": "https://news.example.com/story",
            "canonical_url": "https://news.example.com/story",
            "domain": "news.example.com",
            "title": "",
            "author": "",
            "publish_date": "",
            "content": "",
            "word_count": 0,
            "error": "The news website restricted automated access or is protected by a paywall (HTTP 403). Please paste the article text directly below to verify the claims.",
            "error_code": "FORBIDDEN_OR_PAYWALL",
            "is_homepage": False
        })

        with patch("services.url_extractor.validate_and_resolve_url", return_value=(True, "https://news.example.com/story", None)):
            res = fetch_and_extract_article("https://news.example.com/story")
            self.assertFalse(res["success"])
            self.assertEqual(res["error_code"], "FORBIDDEN_OR_PAYWALL")
            self.assertIn("restricted", res["error"].lower())

    @patch("services.url_extractor._fetch_html_network")
    def test_http_429_rate_limit(self, mock_net):
        """HTTP 429 returns rate-limited error."""
        mock_net.return_value = (False, None, {
            "success": False,
            "url": "https://news.example.com/story",
            "canonical_url": "https://news.example.com/story",
            "domain": "news.example.com",
            "title": "",
            "author": "",
            "publish_date": "",
            "content": "",
            "word_count": 0,
            "error": "The publisher rate limit was reached (HTTP 429). Please wait a moment or paste the text directly.",
            "error_code": "RATE_LIMITED",
            "is_homepage": False
        })

        with patch("services.url_extractor.validate_and_resolve_url", return_value=(True, "https://news.example.com/story", None)):
            res = fetch_and_extract_article("https://news.example.com/story")
            self.assertFalse(res["success"])
            self.assertEqual(res["error_code"], "RATE_LIMITED")
            self.assertIn("rate limit", res["error"].lower())

    # ==============================================================
    # 4. CONTENT EXTRACTION AND TRAFILATURA / BS4 INTEGRATION
    # ==============================================================

    @patch("services.url_extractor._fetch_html_network")
    def test_article_content_extraction_success(self, mock_net):
        """Extract title, body, author, and word count from realistic HTML."""
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Mars Rover Finds Ancient Mineral Formations - Science Daily</title>
          <meta property="og:title" content="Mars Rover Finds Ancient Mineral Formations">
          <meta name="author" content="Dr. Sarah Jenkins">
          <meta property="article:published_time" content="2026-10-09">
        </head>
        <body>
          <nav><a href="/">Home</a><a href="/news">News</a></nav>
          <article>
            <h1>Mars Rover Finds Ancient Mineral Formations</h1>
            <p>NASA's Perseverance rover has identified significant layered sediment deposits on the Jezero Crater floor.</p>
            <p>The geological analysis confirms that water once flowed across this region billions of years ago, creating layered clay minerals.</p>
            <p>Scientists say these core samples will offer deep insights into the atmospheric evolution of ancient Mars.</p>
          </article>
          <footer>Copyright 2026 Science Daily.</footer>
        </body>
        </html>
        """
        mock_net.return_value = (True, sample_html, None)

        with patch("services.url_extractor.validate_and_resolve_url", return_value=(True, "https://example.com/mars-story", None)):
            res = fetch_and_extract_article("https://example.com/mars-story")
            self.assertTrue(res["success"])
            self.assertIn("Perseverance rover", res["content"])
            self.assertGreater(res["word_count"], 20)
            self.assertEqual(res["title"], "Mars Rover Finds Ancient Mineral Formations")

    # ==============================================================
    # 5. REST API & FORM SUBMISSION INTEGRATION
    # ==============================================================

    @patch("app.fetch_and_extract_article")
    def test_api_analyze_url_endpoint_success(self, mock_fetch):
        """POST /api/analyze-url executes verification pipeline and returns structured metadata."""
        mock_fetch.return_value = {
            "success": True,
            "url": "https://example.com/climate",
            "canonical_url": "https://example.com/climate",
            "domain": "example.com",
            "title": "Global Climate Consensus Confirmed",
            "author": "Environmental Desk",
            "publish_date": "2026-10-09",
            "content": "Peer-reviewed scientific studies confirm that global carbon emissions influence planetary atmospheric temperatures.",
            "word_count": 14,
            "error": None,
            "error_code": None,
            "is_homepage": False
        }

        response = self.client.post(
            "/api/analyze-url",
            json={"url": "https://example.com/climate"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["article_fetch_status"], "success")
        self.assertEqual(data["article_title"], "Global Climate Consensus Confirmed")
        self.assertIn("analysis_id", data)
        self.assertIn("prediction", data)
        self.assertIn("verification", data)

    @patch("app.fetch_and_extract_article")
    def test_api_analyze_url_auth_error_response(self, mock_fetch):
        """POST /api/analyze-url returns 400 with AUTH_REQUIRED when target requires login."""
        mock_fetch.return_value = {
            "success": False,
            "url": "https://example.com/paywalled",
            "canonical_url": "https://example.com/paywalled",
            "domain": "example.com",
            "title": "",
            "author": "",
            "publish_date": "",
            "content": "",
            "word_count": 0,
            "error": "The publisher requires subscription authentication or login (HTTP 401). Please paste the article text directly below to verify the claim.",
            "error_code": "AUTH_REQUIRED",
            "is_homepage": False
        }

        response = self.client.post(
            "/api/analyze-url",
            json={"url": "https://example.com/paywalled"}
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "AUTH_REQUIRED")
        self.assertEqual(data["article_fetch_status"], "failed")

    def test_manual_pasted_claim_fallback_works(self):
        """When URL fetching fails, user can submit claim directly via /analyze."""
        response = self.client.post(
            "/analyze",
            data={
                "mode": "claim",
                "text": "Scientific consensus confirms that greenhouse gas emissions drive global climate change."
            },
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Verification Assessment", response.data)
        self.assertIn(b"DistilBERT", response.data)


if __name__ == "__main__":
    unittest.main()
