import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from database import db


class TestAppRoutes(unittest.TestCase):
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

    def test_home_route(self):
        """GET / should render index.html with 200 OK."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"TruthLens AI", response.data)
        self.assertIn(b"Start Claim Analysis", response.data)

    def test_get_analyze_route(self):
        """GET /analyze should render the analysis form with 200 OK."""
        response = self.client.get("/analyze")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Submit Text for Verification", response.data)
        self.assertIn(b"<textarea", response.data)

    def test_post_analyze_empty_input(self):
        """POST /analyze with empty input should return 400 and validation message."""
        response = self.client.post("/analyze", data={"text": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Validation Error", response.data)

    def test_post_analyze_too_short(self):
        """POST /analyze with < 5 characters should return 400."""
        response = self.client.post("/analyze", data={"text": "Hey"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"too short", response.data)

    def test_post_analyze_too_long(self):
        """POST /analyze with text exceeding limit should return 400."""
        too_long = "word " * 3000  # 15,000 chars > 10,000 limit
        response = self.client.post("/analyze", data={"text": too_long})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"exceeds the maximum", response.data)

    def test_post_analyze_and_redirect(self):
        """POST /analyze with valid claim should redirect to /result/<id>."""
        valid_claim = "Tennessee students now cover about 67 percent of the cost of their education."
        response = self.client.post("/analyze", data={"text": valid_claim}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("/result/"))

        # Follow redirect and inspect rendered result page
        result_page = self.client.get(response.location)
        self.assertEqual(result_page.status_code, 200)
        self.assertIn(b"Verification Report", result_page.data)
        self.assertIn(b"Tennessee students", result_page.data)
        self.assertIn(b"Final Assessment", result_page.data)

    def test_view_result_not_found(self):
        """GET /result/<invalid_id> should return 404."""
        response = self.client.get("/result/999999")
        self.assertEqual(response.status_code, 404)

    @patch("services.evidence.WikipediaEvidenceProvider.search")
    def test_evidence_failure_graceful_handling(self, mock_search):
        """If external evidence provider encounters an exception, it must not crash the app."""
        mock_search.side_effect = Exception("Wikipedia network timeout")
        valid_claim = "Scientists have discovered a new planetary system."
        response = self.client.post("/analyze", data={"text": valid_claim}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Verification Report", response.data)
        self.assertIn(b"INSUFFICIENT", response.data)

    def test_history_empty_state(self):
        """GET /history with no records renders history table/empty state with 200 OK."""
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Analysis History", response.data)
        self.assertIn(b"No Analyses Recorded Yet", response.data)

    def test_history_ordering_and_content(self):
        """GET /history displays records ordered newest first with summary attributes."""
        from datetime import datetime, timezone, timedelta
        from database import Analysis

        base_time = datetime.now(timezone.utc)
        rec1 = Analysis(
            input_text="Older claim about economic statistics in 2020",
            predicted_label="False",
            confidence=0.88,
            created_at=base_time - timedelta(minutes=15),
            class_probabilities={"False": 0.88, "Misleading": 0.08, "Reliable": 0.04},
            verification_status="CONTRADICTED"
        )
        rec2 = Analysis(
            input_text="Newer claim about renewable energy generation in 2024",
            predicted_label="Reliable",
            confidence=0.94,
            created_at=base_time,
            class_probabilities={"False": 0.02, "Misleading": 0.04, "Reliable": 0.94},
            verification_status="SUPPORTED"
        )
        db.session.add_all([rec1, rec2])
        db.session.commit()

        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")

        # Verify newest claim appears before older claim in HTML
        pos_newer = content.find("Newer claim about renewable")
        pos_older = content.find("Older claim about economic")
        self.assertTrue(pos_newer != -1 and pos_older != -1)
        self.assertLess(pos_newer, pos_older, "Newest record must appear before older record in history")

        # Verify summary details appear
        self.assertIn("Reliable", content)
        self.assertIn("94.0%", content)
        self.assertIn("SUPPORTED", content)

    def test_history_detail_valid_and_invalid_id(self):
        """GET /history/<valid_id> displays analysis detail; <invalid_id> returns 404."""
        from database import Analysis

        rec = Analysis(
            input_text="Claim for detailed history viewing test",
            predicted_label="Misleading",
            confidence=0.76,
            verification_status="UNVERIFIED",
            evidence_status="insufficient",
            class_probabilities={"False": 0.20, "Misleading": 0.76, "Reliable": 0.04},
            important_phrases=[{"phrase": "history viewing", "importance": 0.5, "direction": "supports_prediction"}],
            explanation_summary="Attribution summary test.",
            evidence_sources=[{"title": "Test Wiki Source", "url": "https://example.com/wiki"}],
            final_assessment="Unverified due to lack of evidence"
        )
        db.session.add(rec)
        db.session.commit()

        # Valid ID on /history/<id>
        res_valid = self.client.get(f"/history/{rec.id}")
        self.assertEqual(res_valid.status_code, 200)
        self.assertIn(b"Verification Report", res_valid.data)
        self.assertIn(b"Claim for detailed history viewing test", res_valid.data)
        self.assertIn(b"Misleading", res_valid.data)
        self.assertIn(b"Test Wiki Source", res_valid.data)

        # Invalid ID on /history/<id>
        res_invalid = self.client.get("/history/888888")
        self.assertEqual(res_invalid.status_code, 404)

        # Non-numeric ID returns 404
        res_bad_id = self.client.get("/history/invalid-id")
        self.assertEqual(res_bad_id.status_code, 404)

    def test_result_and_history_consistency(self):
        """Verify /result/<id> and /history/<id> render identical content for the same record."""
        from database import Analysis

        rec = Analysis(
            input_text="Identical rendering test claim",
            predicted_label="Reliable",
            confidence=0.92,
            verification_status="SUPPORTED",
            evidence_status="supporting",
            class_probabilities={"False": 0.03, "Misleading": 0.05, "Reliable": 0.92},
            important_phrases=[{"phrase": "identical", "importance": 0.6, "direction": "supports_prediction"}],
            evidence_sources=[{"title": "Corroboration source", "url": "https://example.com"}]
        )
        db.session.add(rec)
        db.session.commit()

        res_result = self.client.get(f"/result/{rec.id}")
        res_history = self.client.get(f"/history/{rec.id}")

        self.assertEqual(res_result.status_code, 200)
        self.assertEqual(res_history.status_code, 200)
        self.assertEqual(res_result.data, res_history.data)


if __name__ == "__main__":
    unittest.main()
