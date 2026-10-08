import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from database import db


class TestApiEndpoints(unittest.TestCase):
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

    def test_api_health(self):
        """GET /api/health returns 200 with system health details without leaking secrets."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["model"], "distilbert-base-uncased")
        self.assertEqual(data["classes"], ["False", "Misleading", "Reliable"])
        self.assertIn("version", data)
        self.assertIn("evidence_provider", data)
        # Ensure no secret or local filesystem path leaks
        data_str = str(data)
        self.assertNotIn("SECRET_KEY", data_str)
        self.assertNotIn("C:\\", data_str)
        self.assertNotIn("/Users/", data_str)

    def test_api_analyze_missing_json_header(self):
        """POST /api/analyze without application/json returns 400."""
        response = self.client.post("/api/analyze", data="plain text body")
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("valid JSON", data["error"])

    def test_api_analyze_missing_text_field(self):
        """POST /api/analyze with JSON missing 'text' field returns 400."""
        response = self.client.post("/api/analyze", json={"other_field": "test"})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("required", data["error"])

    def test_api_analyze_empty_text(self):
        """POST /api/analyze with empty text string returns 400."""
        response = self.client.post("/api/analyze", json={"text": "   "})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("empty", data["error"])

    def test_api_analyze_too_short(self):
        """POST /api/analyze with < 5 chars returns 400."""
        response = self.client.post("/api/analyze", json={"text": "No"})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("too short", data["error"])

    def test_api_analyze_exceeds_max_length(self):
        """POST /api/analyze with text exceeding max limit returns 413."""
        long_text = "word " * 2500  # 12,500 characters > 10,000 limit
        response = self.client.post("/api/analyze", json={"text": long_text})
        self.assertEqual(response.status_code, 413)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertIn("exceeds the maximum", data["error"])

    def test_api_analyze_valid_claim(self):
        """POST /api/analyze with valid claim returns 200 and full verification result."""
        claim = "George Washington was the first President of the United States."
        response = self.client.post("/api/analyze", json={"text": claim})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertTrue(data["success"])
        self.assertIn("analysis_id", data)
        self.assertIsInstance(data["analysis_id"], int)
        self.assertGreater(data["analysis_id"], 0)

        # Verify record exists in SQLite database
        from database import Analysis
        persisted = db.session.get(Analysis, data["analysis_id"])
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.input_text, claim)

        analysis = data["analysis"]

        # Validate structured fields
        self.assertIn("claim", analysis)
        self.assertIn("prediction", analysis)
        self.assertIn("label", analysis["prediction"])
        self.assertIn(analysis["prediction"]["label"], ["False", "Misleading", "Reliable"])
        self.assertIsInstance(analysis["prediction"]["confidence"], float)

        self.assertIn("probabilities", analysis)
        self.assertIn("False", analysis["probabilities"])
        self.assertIn("Misleading", analysis["probabilities"])
        self.assertIn("Reliable", analysis["probabilities"])

        self.assertIn("explanation", analysis)
        self.assertIn("summary", analysis["explanation"])
        self.assertIn("confidence_status", analysis["explanation"])
        self.assertIn("important_phrases", analysis["explanation"])

        self.assertIn("evidence", analysis)
        self.assertIn("status", analysis["evidence"])
        self.assertIn(analysis["evidence"]["status"], ["supporting", "contradicting", "insufficient"])
        self.assertIn("sources", analysis["evidence"])

        self.assertIn("verification", analysis)
        self.assertIn("result", analysis["verification"])
        self.assertIn("status", analysis["verification"])

        self.assertIn("responsible_ai", analysis)
        self.assertIn("confidence_note", analysis["responsible_ai"])
        self.assertIn("verification_note", analysis["responsible_ai"])

    @patch("services.evidence.WikipediaEvidenceProvider.search")
    def test_api_analyze_external_evidence_failure(self, mock_search):
        """If external evidence network search raises an exception, the API does not crash."""
        mock_search.side_effect = TimeoutError("Simulated external network timeout")
        claim = "Vaccines cause autism in children."
        response = self.client.post("/api/analyze", json={"text": claim})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        # Should gracefully return insufficient status
        self.assertEqual(data["analysis"]["evidence"]["status"], "insufficient")


if __name__ == "__main__":
    unittest.main()
