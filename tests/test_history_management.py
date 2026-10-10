# tests/test_history_management.py
"""Comprehensive test suite for Phase 14C: History Management & Safe Deletion in TruthLens AI."""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app, get_dashboard_metrics
from database import db, Analysis, delete_analysis, clear_history, get_analysis


class TestHistoryManagement(unittest.TestCase):
    """Test suite verifying individual record deletion, clear history, and dashboard updates."""

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

    def _seed_sample_records(self, count=3):
        """Helper to create test analysis records."""
        records = []
        for i in range(1, count + 1):
            rec = Analysis(
                input_text=f"Sample claim #{i} for testing history management.",
                predicted_label="Reliable" if i % 2 == 0 else "False",
                confidence=0.85 + (i * 0.02),
                verification_status="SUPPORTED" if i % 2 == 0 else "REFUTED",
                evidence_status="supporting" if i % 2 == 0 else "contradicting",
                class_probabilities={"False": 0.1, "Misleading": 0.1, "Reliable": 0.8},
                important_phrases=[{"phrase": f"keyword_{i}", "importance": 0.3}],
                explanation_summary=f"Summary for sample #{i}",
                evidence_summary=f"Evidence for sample #{i}",
                evidence_sources=[{"title": f"Source #{i}", "url": f"https://example.com/{i}"}],
                final_assessment=f"Final assessment #{i}",
                conflict_detected=False
            )
            db.session.add(rec)
            records.append(rec)
        db.session.commit()
        return records

    def test_1_individual_deletion_removes_selected_record(self):
        """1. Individual deletion removes the selected record from the database."""
        records = self._seed_sample_records(3)
        target_id = records[1].id

        self.assertIsNotNone(get_analysis(target_id))
        deleted = delete_analysis(target_id)
        self.assertTrue(deleted)
        self.assertIsNone(get_analysis(target_id))

    def test_2_individual_deletion_preserves_other_records(self):
        """2. Individual deletion preserves all other records."""
        records = self._seed_sample_records(4)
        target_id = records[1].id
        keep_ids = [records[0].id, records[2].id, records[3].id]

        response = self.client.post(f"/history/{target_id}/delete", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Confirm deleted record is gone
        self.assertIsNone(get_analysis(target_id))

        # Confirm other records remain intact
        for k_id in keep_ids:
            self.assertIsNotNone(get_analysis(k_id), f"Record #{k_id} should have been preserved.")

    def test_3_cancelling_deletion_preserves_record(self):
        """3. No deletion occurs without explicit confirmation submission."""
        records = self._seed_sample_records(2)
        rec_id = records[0].id

        # Simulating user browsing history or cancelling (no POST)
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Historical Verifications", response.data)
        self.assertIsNotNone(get_analysis(rec_id))

    def test_4_clear_history_removes_all_records(self):
        """4. Clear history deletes all analysis records cleanly."""
        self._seed_sample_records(5)
        self.assertEqual(Analysis.query.count(), 5)

        response = self.client.post("/history/clear", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Analysis.query.count(), 0)
        self.assertIn(b"No Verification Records Found", response.data)

    def test_5_cancelling_clear_history_preserves_records(self):
        """5. Without POST to /history/clear, every record is preserved."""
        self._seed_sample_records(3)
        self.assertEqual(Analysis.query.count(), 3)

        # GET request to /history
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Analysis.query.count(), 3)

    def test_6_empty_history_renders_correctly(self):
        """6. Empty history page renders a friendly empty state without errors."""
        self.assertEqual(Analysis.query.count(), 0)
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No Verification Records Found", response.data)
        self.assertIn(b"Analyze First Claim", response.data)

    def test_7_invalid_record_ids_handled_safely(self):
        """7. Non-existent and non-integer IDs are handled gracefully with 404 or redirect."""
        # Non-existent integer ID
        resp_web = self.client.post("/history/999999/delete", follow_redirects=True)
        self.assertEqual(resp_web.status_code, 200)

        # Non-integer ID on delete
        resp_bad_id = self.client.post("/history/abc_invalid/delete", follow_redirects=True)
        self.assertEqual(resp_bad_id.status_code, 200)

        # API call with non-existent ID returns JSON 404
        resp_api = self.client.delete("/api/history/999999")
        self.assertEqual(resp_api.status_code, 404)
        data = resp_api.get_json()
        self.assertFalse(data["success"])

    def test_8_unsupported_get_requests_do_not_delete(self):
        """8. GET requests to deletion endpoints do not delete records."""
        records = self._seed_sample_records(2)
        rec_id = records[0].id

        # Attempt GET on delete web route - should redirect to /history without deleting
        resp_get = self.client.get(f"/history/{rec_id}/delete", follow_redirects=True)
        self.assertEqual(resp_get.status_code, 200)
        self.assertIsNotNone(get_analysis(rec_id), "Record should NOT be deleted via GET request")

        # Attempt GET on API delete route - should return 405 Method Not Allowed
        resp_api_get = self.client.get(f"/api/history/{rec_id}")
        self.assertIn(resp_api_get.status_code, [404, 405])
        self.assertIsNotNone(get_analysis(rec_id))

        # Attempt GET on clear route - should redirect to /history without clearing
        resp_get_clear = self.client.get("/history/clear", follow_redirects=True)
        self.assertEqual(resp_get_clear.status_code, 200)
        self.assertEqual(Analysis.query.count(), 2, "Records should NOT be cleared via GET request")

    def test_9_database_schema_remains_valid_after_deletions(self):
        """9. Schema and table remain intact after individual deletion and clear operations."""
        self._seed_sample_records(3)
        clear_history()
        self.assertEqual(Analysis.query.count(), 0)

        # Insert new record into existing table to confirm schema validity
        new_rec = Analysis(
            input_text="Post-clear verification test claim.",
            predicted_label="Reliable",
            confidence=0.92,
            verification_status="SUPPORTED",
            evidence_status="supporting",
            class_probabilities={"False": 0.05, "Misleading": 0.03, "Reliable": 0.92}
        )
        db.session.add(new_rec)
        db.session.commit()
        self.assertEqual(Analysis.query.count(), 1)

    def test_10_dashboard_metrics_update_after_deletion(self):
        """10. Dashboard metrics update accurately following deletions."""
        self._seed_sample_records(4)
        metrics_before = get_dashboard_metrics()
        self.assertEqual(metrics_before["total_count"], 4)

        # Delete one record
        first_id = Analysis.query.first().id
        delete_analysis(first_id)

        metrics_after_one = get_dashboard_metrics()
        self.assertEqual(metrics_after_one["total_count"], 3)

        # Clear remaining records
        clear_history()
        metrics_empty = get_dashboard_metrics()
        self.assertEqual(metrics_empty["total_count"], 0)
        self.assertEqual(metrics_empty["reliable_count"], 0)
        self.assertEqual(metrics_empty["false_count"], 0)
        self.assertEqual(metrics_empty["average_confidence_pct"], 0.0)

    def test_11_result_page_for_deleted_record_returns_404(self):
        """11. Result and history detail pages for deleted records gracefully return 404."""
        records = self._seed_sample_records(1)
        rec_id = records[0].id

        # Verify page loads when record exists
        resp_before = self.client.get(f"/result/{rec_id}")
        self.assertEqual(resp_before.status_code, 200)

        # Delete the record
        delete_analysis(rec_id)

        # Verify graceful 404 page
        resp_after = self.client.get(f"/result/{rec_id}")
        self.assertEqual(resp_after.status_code, 404)
        self.assertIn(b"Record Not Found", resp_after.data)

        resp_hist_after = self.client.get(f"/history/{rec_id}")
        self.assertEqual(resp_hist_after.status_code, 404)
        self.assertIn(b"Record Not Found", resp_hist_after.data)

    def test_12_api_history_endpoints_work_properly(self):
        """12. JSON API endpoints for DELETE /api/history/<id> and /api/history/clear function correctly."""
        records = self._seed_sample_records(3)
        target_id = records[0].id

        # Test DELETE /api/history/<id>
        resp_del = self.client.delete(f"/api/history/{target_id}")
        self.assertEqual(resp_del.status_code, 200)
        json_del = resp_del.get_json()
        self.assertTrue(json_del["success"])
        self.assertEqual(json_del["deleted_id"], target_id)

        # Test POST /api/history/clear
        resp_clear = self.client.post("/api/history/clear")
        self.assertEqual(resp_clear.status_code, 200)
        json_clear = resp_clear.get_json()
        self.assertTrue(json_clear["success"])
        self.assertEqual(json_clear["deleted_count"], 2)

    def test_13_form_body_deletion_works(self):
        """13. POST /history/delete with record_id in form body deletes targeted record."""
        records = self._seed_sample_records(3)
        target_id = records[1].id
        keep_ids = [records[0].id, records[2].id]

        response = self.client.post("/history/delete", data={"record_id": str(target_id)}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Confirm deleted record is gone
        self.assertIsNone(get_analysis(target_id))

        # Confirm others remain
        for k_id in keep_ids:
            self.assertIsNotNone(get_analysis(k_id))

    def test_14_database_rollback_on_error(self):
        """14. Database operations roll back cleanly upon unexpected exception."""
        records = self._seed_sample_records(2)
        initial_count = Analysis.query.count()

        # Monkey-patch db.session.delete to simulate unexpected database failure
        orig_delete = db.session.delete
        try:
            def faulty_delete(obj):
                raise RuntimeError("Simulated database failure")
            db.session.delete = faulty_delete

            with self.assertRaises(RuntimeError):
                delete_analysis(records[0].id)
            
            # Confirm record was NOT deleted
            self.assertEqual(Analysis.query.count(), initial_count)
        finally:
            db.session.delete = orig_delete


if __name__ == "__main__":
    unittest.main()

