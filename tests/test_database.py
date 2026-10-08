import os
import sys
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from database import db, Analysis, init_db, utc_now


class TestDatabase(unittest.TestCase):
    """Test suite for TruthLens AI SQLite database and Analysis model persistence."""

    def setUp(self):
        # Initialize test app with isolated in-memory test database
        self.app = create_app("testing")
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_1_database_initialization(self):
        """1. Database initialization succeeds with app context."""
        self.assertIsNotNone(db)
        self.assertEqual(self.app.config["SQLALCHEMY_DATABASE_URI"], "sqlite:///:memory:")

    def test_2_table_creation(self):
        """2. Table creation creates 'analysis' table with expected schema."""
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        self.assertIn("analysis", tables)

        columns = {col["name"]: col for col in inspector.get_columns("analysis")}
        required_cols = [
            "id", "created_at", "input_text", "predicted_label",
            "confidence", "verification_status", "evidence_status",
            "class_probabilities", "important_phrases", "evidence_sources"
        ]
        for col in required_cols:
            self.assertIn(col, columns, f"Expected column {col} in analysis table")

    def test_3_insert_analysis(self):
        """3. Insert analysis record with complete attributes."""
        record = Analysis(
            input_text="The Earth orbits the Sun.",
            predicted_label="Reliable",
            confidence=0.985,
            verification_status="SUPPORTED",
            evidence_status="supporting",
            class_probabilities={"False": 0.01, "Misleading": 0.005, "Reliable": 0.985},
            important_phrases=[{"phrase": "orbits", "importance": 0.45, "direction": "supports_prediction"}],
            explanation_summary="High confidence scientific statement.",
            evidence_summary="Astronomical fact verified by multiple sources.",
            evidence_sources=[{"title": "Earth's orbit", "url": "https://en.wikipedia.org/wiki/Earth%27s_orbit"}],
            final_assessment="Verified by external sources",
            conflict_detected=False
        )
        db.session.add(record)
        db.session.commit()

        self.assertIsNotNone(record.id)
        self.assertGreater(record.id, 0)
        self.assertIsNotNone(record.created_at)

    def test_4_retrieve_analysis(self):
        """4. Retrieve multiple persisted analysis records."""
        rec1 = Analysis(
            input_text="Claim A",
            predicted_label="False",
            confidence=0.88,
            verification_status="CONTRADICTED",
            evidence_status="contradicting",
            class_probabilities={"False": 0.88, "Misleading": 0.07, "Reliable": 0.05}
        )
        rec2 = Analysis(
            input_text="Claim B",
            predicted_label="Reliable",
            confidence=0.92,
            verification_status="SUPPORTED",
            evidence_status="supporting",
            class_probabilities={"False": 0.02, "Misleading": 0.06, "Reliable": 0.92}
        )
        db.session.add_all([rec1, rec2])
        db.session.commit()

        records = Analysis.query.all()
        self.assertEqual(len(records), 2)
        claims = [r.input_text for r in records]
        self.assertIn("Claim A", claims)
        self.assertIn("Claim B", claims)

    def test_5_retrieve_analysis_by_id(self):
        """5. Retrieve specific analysis record by ID."""
        rec = Analysis(
            input_text="Specific Claim to retrieve",
            predicted_label="Misleading",
            confidence=0.74,
            verification_status="UNVERIFIED",
            evidence_status="insufficient",
            class_probabilities={"False": 0.20, "Misleading": 0.74, "Reliable": 0.06}
        )
        db.session.add(rec)
        db.session.commit()

        fetched = db.session.get(Analysis, rec.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.input_text, "Specific Claim to retrieve")
        self.assertEqual(fetched.predicted_label, "Misleading")
        self.assertAlmostEqual(fetched.confidence, 0.74, places=2)

    def test_6_history_ordering(self):
        """6. History ordering strictly orders newest records first."""
        base_time = datetime.now(timezone.utc)
        rec1 = Analysis(
            input_text="Old claim",
            predicted_label="False",
            confidence=0.80,
            created_at=base_time - timedelta(minutes=10),
            class_probabilities={"False": 0.8, "Misleading": 0.1, "Reliable": 0.1}
        )
        rec2 = Analysis(
            input_text="Mid claim",
            predicted_label="Reliable",
            confidence=0.85,
            created_at=base_time - timedelta(minutes=5),
            class_probabilities={"False": 0.1, "Misleading": 0.05, "Reliable": 0.85}
        )
        rec3 = Analysis(
            input_text="Newest claim",
            predicted_label="Misleading",
            confidence=0.70,
            created_at=base_time,
            class_probabilities={"False": 0.2, "Misleading": 0.7, "Reliable": 0.1}
        )
        db.session.add_all([rec1, rec2, rec3])
        db.session.commit()

        ordered = Analysis.query.order_by(Analysis.created_at.desc()).all()
        self.assertEqual(len(ordered), 3)
        self.assertEqual(ordered[0].input_text, "Newest claim")
        self.assertEqual(ordered[1].input_text, "Mid claim")
        self.assertEqual(ordered[2].input_text, "Old claim")

    def test_7_json_serialization_roundtrip(self):
        """7. JSON serialization/deserialization for probabilities, phrases, and sources."""
        phrases_data = [
            {"phrase": "breaking news", "importance": 0.65, "direction": "supports_prediction"},
            {"phrase": "unconfirmed", "importance": 0.35, "direction": "opposes_prediction"}
        ]
        sources_data = [
            {"title": "Fact Check #1", "url": "https://example.com/1", "relation": "contradicting"},
            {"title": "Fact Check #2", "url": "https://example.com/2", "relation": "supporting"}
        ]
        probs_data = {"False": 0.75, "Misleading": 0.20, "Reliable": 0.05}

        rec = Analysis(
            input_text="Claim with rich structured JSON",
            predicted_label="False",
            confidence=0.75,
            class_probabilities=probs_data,
            important_phrases=phrases_data,
            evidence_sources=sources_data
        )
        db.session.add(rec)
        db.session.commit()

        fetched = db.session.get(Analysis, rec.id)
        d = fetched.to_dict()

        # Validate deserialization back to dict/list
        self.assertEqual(d["probabilities"]["False"], 0.75)
        self.assertEqual(len(d["explanation"]["important_phrases"]), 2)
        self.assertEqual(d["explanation"]["important_phrases"][0]["phrase"], "breaking news")
        self.assertEqual(len(d["evidence"]["sources"]), 2)
        self.assertEqual(d["evidence"]["sources"][0]["title"], "Fact Check #1")

    def test_8_missing_optional_fields(self):
        """8. Missing/null optional fields deserialize gracefully with safe defaults."""
        rec = Analysis(
            input_text="Minimal claim",
            predicted_label="Reliable",
            confidence=0.91,
            class_probabilities={"False": 0.01, "Misleading": 0.08, "Reliable": 0.91},
            important_phrases=None,
            explanation_summary=None,
            evidence_summary=None,
            evidence_sources=None,
            final_assessment=None
        )
        db.session.add(rec)
        db.session.commit()

        fetched = db.session.get(Analysis, rec.id)
        # to_dict should not raise and supply safe defaults
        d = fetched.to_dict()
        self.assertEqual(d["explanation"]["important_phrases"], [])
        self.assertIn("Explanation", d["explanation"]["summary"])
        self.assertEqual(d["evidence"]["sources"], [])
        self.assertEqual(d["evidence"]["status"], "insufficient")
        self.assertEqual(d["verification"]["result"], "Unverified")

        # to_summary_dict should also handle missing fields safely
        summary = fetched.to_summary_dict()
        self.assertEqual(summary["claim_short"], "Minimal claim")
        self.assertEqual(summary["predicted_label"], "Reliable")
        self.assertEqual(summary["verification_status"], "UNVERIFIED")

    def test_9_persistence_across_app_contexts(self):
        """9. Persistence survives across independent application contexts."""
        rec = Analysis(
            input_text="Cross-context persistence claim",
            predicted_label="False",
            confidence=0.95,
            class_probabilities={"False": 0.95, "Misleading": 0.03, "Reliable": 0.02}
        )
        db.session.add(rec)
        db.session.commit()
        saved_id = rec.id

        # Pop current context and simulate a new request/worker context
        self.ctx.pop()

        new_ctx = self.app.app_context()
        new_ctx.push()
        try:
            fetched = db.session.get(Analysis, saved_id)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.input_text, "Cross-context persistence claim")
            self.assertEqual(fetched.predicted_label, "False")
        finally:
            new_ctx.pop()
            self.ctx.push()

    def test_database_integrity_constraints(self):
        """Ensure required non-null fields raise IntegrityError when missing."""
        bad_rec = Analysis(
            input_text=None,  # Nullable=False
            predicted_label="Reliable",
            confidence=0.90,
            class_probabilities={"Reliable": 0.9}
        )
        db.session.add(bad_rec)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()


if __name__ == "__main__":
    unittest.main()
