"""tests/test_phase13a_evidence_first.py
Comprehensive test suite for Phase 13A Evidence-First Verification Layer.
Validates multi-query extraction, live evidence quality scoring, stance classification,
evidence-first decision matrix, resilience, and real-time processing of new content.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from database import db, Analysis
from services.claim_extractor import (
    extract_claim,
    extract_claims_from_text,
    generate_search_queries,
    extract_entities,
    clean_claim_text
)
from services.evidence import (
    search_evidence,
    determine_relation,
    calculate_relevance,
    GoogleFactCheckProvider,
    WikipediaEvidenceProvider
)
from services.verification import verify_claim, synthesize_verification


class TestPhase13AEvidenceFirst(unittest.TestCase):
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
    # 1. MULTI-QUERY & ENTITY EXTRACTION
    # ==============================================================

    def test_generate_multiple_queries_deduplication(self):
        """Claim extractor generates 2 to 4 diverse, deduplicated search queries."""
        claim = "NASA discovered evidence of liquid water on Mars during recent rover explorations."
        queries = generate_search_queries(claim, max_queries=4)
        self.assertTrue(2 <= len(queries) <= 4)
        # Check no duplicate query strings
        self.assertEqual(len(queries), len(set(q.lower() for q in queries)))

    def test_extract_entities_from_claim(self):
        """Entity extractor identifies proper nouns, organizations, and dates."""
        text = "In 1789, George Washington became the first President under NASA guidelines."
        entities_data = extract_entities(text)
        entities = entities_data.get("entities", [])
        self.assertIn("George Washington", entities)
        self.assertIn("NASA", entities)
        self.assertTrue(any("1789" in d for d in entities_data.get("dates", [])))

    def test_extract_claims_from_long_article(self):
        """Long multi-paragraph text is decomposed into individual factual claims."""
        article = (
            "Global renewable energy capacity grew by 50 percent in 2023. "
            "The International Energy Agency reported historic solar installations across Europe and Asia. "
            "However, fossil fuel subsidies reached record levels in several emerging markets."
        )
        claims = extract_claims_from_text(article)
        self.assertTrue(len(claims) >= 2)
        for c in claims:
            self.assertIn("claim", c)
            self.assertIn("queries", c)
            self.assertTrue(len(c["queries"]) >= 1)

    # ==============================================================
    # 2. EVIDENCE STANCE & QUALITY SCORING
    # ==============================================================

    def test_stance_supporting(self):
        """Affirmative authoritative statements are classified as supporting."""
        claim = "George Washington was the first President of the United States."
        source = {
            "title": "George Washington",
            "snippet": "George Washington was an American military officer, statesman, and the first president of the United States.",
            "source": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/George_Washington"
        }
        stance = determine_relation(claim, source)
        self.assertEqual(stance, "supports")

    def test_stance_contradicting_comparative(self):
        """Astronomical and superlative factual contradictions are classified as contradicts."""
        claim = "Earth is the largest planet in the solar system."
        source = {
            "title": "Jupiter",
            "snippet": "Jupiter is the largest planet in the Solar System. It is an astronomical gas giant with a mass more than two and a half times that of all other planets.",
            "source": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/Jupiter"
        }
        stance = determine_relation(claim, source)
        self.assertEqual(stance, "contradicts")

    def test_stance_contradicting_debunked_claim(self):
        """Disproven or debunked assertions are classified as contradicts."""
        claim = "Childhood vaccines cause autism in children."
        source = {
            "title": "MMR vaccine and autism",
            "snippet": "Extensive scientific investigations have found no link between the MMR vaccine and autism. The original claims have been debunked and retracted as fraudulent.",
            "source": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/MMR_vaccine_and_autism"
        }
        stance = determine_relation(claim, source)
        self.assertEqual(stance, "contradicts")

    def test_stance_irrelevant(self):
        """Low relevance sources are classified as irrelevant."""
        claim = "Zorblax City officially declared every Tuesday a national holiday."
        source = {
            "title": "Tuesday",
            "snippet": "Tuesday is the day of the week between Monday and Wednesday.",
            "source": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/Tuesday"
        }
        stance = determine_relation(claim, source)
        self.assertIn(stance, ("irrelevant", "neutral"))

    # ==============================================================
    # 3. EVIDENCE-FIRST DECISION MATRIX
    # ==============================================================

    def test_decision_matrix_insufficient_evidence_never_forces_false(self):
        """When evidence is insufficient, verdict is UNVERIFIED, never forced to False."""
        res = synthesize_verification(pred_label="False", confidence=0.88, evidence_status="insufficient")
        self.assertEqual(res["status"], "UNVERIFIED")
        self.assertIn("Insufficient Evidence", res["result"])

    def test_decision_matrix_supporting_evidence(self):
        """Reliable prediction with supporting evidence results in SUPPORTED."""
        res = synthesize_verification(pred_label="Reliable", confidence=0.90, evidence_status="supporting")
        self.assertEqual(res["status"], "SUPPORTED")
        self.assertFalse(res["conflict_detected"])

    def test_decision_matrix_contradicting_evidence(self):
        """Contradicting evidence results in LIKELY_FALSE."""
        res = synthesize_verification(pred_label="False", confidence=0.85, evidence_status="contradicting")
        self.assertEqual(res["status"], "LIKELY_FALSE")

    def test_decision_matrix_conflicting_signals(self):
        """Model prediction False with Supporting evidence triggers CONFLICTING_SIGNALS."""
        res = synthesize_verification(pred_label="False", confidence=0.80, evidence_status="supporting")
        self.assertEqual(res["status"], "CONFLICTING_SIGNALS")
        self.assertTrue(res["conflict_detected"])

    def test_decision_matrix_mixed_evidence(self):
        """Mixed / contested evidence results in MISLEADING."""
        res = synthesize_verification(pred_label="Reliable", confidence=0.70, evidence_status="mixed")
        self.assertEqual(res["status"], "MISLEADING")

    # ==============================================================
    # 4. GOOGLE FACT CHECK PROVIDER GRACEFUL DEGRADATION
    # ==============================================================

    def test_google_provider_unavailable_without_key(self):
        """Google Fact Check provider returns is_available=False when API key is unset."""
        with patch.dict("os.environ", {}, clear=True):
            provider = GoogleFactCheckProvider(api_key="")
            self.assertFalse(provider.is_available())
            self.assertEqual(provider.search("test claim"), [])

    # ==============================================================
    # 5. REAL TIME & TIMESTAMPS
    # ==============================================================

    def test_evidence_returns_real_iso_timestamp(self):
        """Live evidence retrieval records real ISO 8601 UTC timestamp."""
        res = search_evidence("Water is a chemical compound consisting of hydrogen and oxygen.")
        self.assertIn("retrieved_at", res)
        # Verify valid parseable ISO format
        dt = datetime.fromisoformat(res["retrieved_at"])
        self.assertIsNotNone(dt)

    # ==============================================================
    # 6. VERIFY_CLAIM PIPELINE END-TO-END ON NEW CONTENT
    # ==============================================================

    def test_verify_new_claim_end_to_end(self):
        """End-to-end pipeline verification on fresh new claim."""
        claim = "George Washington was the first President of the United States."
        result = verify_claim(claim)
        self.assertIn("George Washington was the first President", result["claim"])
        self.assertIn("prediction", result)
        self.assertIn("evidence", result)
        self.assertIn("verification", result)
        self.assertIn("sources", result["evidence"])
        self.assertIn("supporting_count", result["evidence"])

    def test_verify_random_unverifiable_claim(self):
        """Fictional claim with no external records returns UNVERIFIED."""
        claim = "Zorblax City officially declared every Tuesday a national holiday."
        result = verify_claim(claim)
        self.assertEqual(result["verification"]["status"], "UNVERIFIED")
        self.assertEqual(result["evidence"]["status"], "insufficient")


if __name__ == "__main__":
    unittest.main()
