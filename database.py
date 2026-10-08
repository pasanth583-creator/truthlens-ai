# database.py
"""SQLAlchemy database models and initialization for TruthLens AI.
Handles persistence of analysis requests, predictions, explainability tokens,
and external verification results.
"""
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from flask_sqlalchemy import SQLAlchemy

# SQLAlchemy instance - initialized in app.py
db = SQLAlchemy()


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Analysis(db.Model):
    """Persistence model for an end-to-end verification analysis record."""
    __tablename__ = "analysis"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    input_text = db.Column(db.Text, nullable=False)
    predicted_label = db.Column(db.String(50), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    verification_status = db.Column(db.String(50), nullable=False, default="UNVERIFIED")
    evidence_status = db.Column(db.String(50), nullable=False, default="insufficient")

    # Structured JSON data (stored as JSON/Text)
    class_probabilities = db.Column(db.JSON, nullable=False)
    important_phrases = db.Column(db.JSON, nullable=True)
    explanation_summary = db.Column(db.Text, nullable=True)
    evidence_summary = db.Column(db.Text, nullable=True)
    evidence_sources = db.Column(db.JSON, nullable=True)
    final_assessment = db.Column(db.Text, nullable=True)
    conflict_detected = db.Column(db.Boolean, default=False)

    # Backward compatibility properties
    @property
    def prediction(self) -> str:
        return self.predicted_label

    @prediction.setter
    def prediction(self, val: str):
        self.predicted_label = val

    @property
    def recommendation(self) -> Optional[str]:
        return self.final_assessment

    @recommendation.setter
    def recommendation(self, val: Optional[str]):
        self.final_assessment = val

    @property
    def explanation(self) -> Optional[str]:
        return self.explanation_summary

    @explanation.setter
    def explanation(self, val: Optional[str]):
        self.explanation_summary = val

    @property
    def suspicious_phrases(self) -> Any:
        return self.important_phrases

    @suspicious_phrases.setter
    def suspicious_phrases(self, val: Any):
        if isinstance(val, str):
            try:
                self.important_phrases = json.loads(val)
            except Exception:
                self.important_phrases = []
        else:
            self.important_phrases = val

    @property
    def evidence(self) -> Any:
        return self.evidence_sources

    @evidence.setter
    def evidence(self, val: Any):
        if isinstance(val, str):
            try:
                self.evidence_sources = json.loads(val)
            except Exception:
                self.evidence_sources = []
        else:
            self.evidence_sources = val

    def to_dict(self) -> Dict[str, Any]:
        """Safely deserialize record to standardized verification dictionary."""
        # Safe JSON decoding for fields that might be strings or None
        def safe_json(val, default):
            if val is None:
                return default
            if isinstance(val, (dict, list)):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return default
            return default

        raw_probs = safe_json(self.class_probabilities, {"False": 0.0, "Misleading": 0.0, "Reliable": 0.0})
        probs = {}
        if isinstance(raw_probs, dict):
            for k in ["False", "Misleading", "Reliable"]:
                try:
                    probs[k] = float(raw_probs.get(k, 0.0))
                except (TypeError, ValueError):
                    probs[k] = 0.0
        else:
            probs = {"False": 0.0, "Misleading": 0.0, "Reliable": 0.0}

        raw_phrases = safe_json(self.important_phrases, [])
        phrases = []
        if isinstance(raw_phrases, list):
            for p in raw_phrases:
                if isinstance(p, dict):
                    try:
                        imp = float(p.get("importance", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        imp = 0.0
                    phrases.append({
                        "phrase": str(p.get("phrase", "")),
                        "importance": imp,
                        "direction": str(p.get("direction", "supports_prediction"))
                    })

        raw_sources = safe_json(self.evidence_sources, [])
        sources = []
        if isinstance(raw_sources, list):
            for s in raw_sources:
                if isinstance(s, dict):
                    try:
                        rel = float(s.get("relevance_score", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        rel = 0.0
                    sources.append({
                        "title": str(s.get("title", "External Reference")),
                        "source": str(s.get("source", "Reference")),
                        "relation": str(s.get("relation", "unspecified")),
                        "relevance_score": rel,
                        "snippet": str(s.get("snippet", "")),
                        "url": str(s.get("url", "#"))
                    })

        # Format created_at nicely
        created_str = ""
        if self.created_at:
            try:
                created_str = self.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                created_str = str(self.created_at)

        conf_val = 0.0
        try:
            conf_val = float(self.confidence)
        except (TypeError, ValueError):
            conf_val = 0.0

        conf_status = "Model prediction" if conf_val >= 0.60 else "Low confidence"

        return {
            "id": self.id,
            "claim": self.input_text or "",
            "created_at": created_str,
            "prediction": {
                "label": self.predicted_label or "Unknown",
                "confidence": round(conf_val, 4)
            },
            "probabilities": probs,
            "explanation": {
                "summary": self.explanation_summary or "Explanation generated from token attribution.",
                "confidence_status": conf_status,
                "important_phrases": phrases
            },
            "evidence": {
                "status": self.evidence_status or "insufficient",
                "summary": self.evidence_summary or "External evidence record.",
                "sources": sources
            },
            "verification": {
                "status": self.verification_status or "UNVERIFIED",
                "result": self.final_assessment or "Unverified",
                "conflict_detected": bool(self.conflict_detected),
                "assessment_note": ""
            },
            "responsible_ai": {
                "confidence_note": "Model confidence is not factual certainty.",
                "verification_note": "Evidence retrieval is separate from the classifier prediction. When evidence is insufficient, the claim remains unverified."
            }
        }

    def to_summary_dict(self) -> Dict[str, Any]:
        """Return a compact summary suitable for history list views."""
        text = self.input_text or ""
        shortened_claim = text[:90] + ("..." if len(text) > 90 else "")
        created_str = ""
        if self.created_at:
            try:
                created_str = self.created_at.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                created_str = str(self.created_at)

        conf_val = 0.0
        try:
            conf_val = float(self.confidence)
        except (TypeError, ValueError):
            conf_val = 0.0

        return {
            "id": self.id,
            "created_at": created_str,
            "claim_short": shortened_claim,
            "claim_full": text,
            "predicted_label": self.predicted_label or "Unknown",
            "confidence": round(conf_val, 4),
            "verification_status": self.verification_status or "UNVERIFIED",
            "evidence_status": self.evidence_status or "insufficient",
            "conflict_detected": bool(self.conflict_detected)
        }


def init_db(app=None):
    """Create tables if they do not exist."""
    if app:
        with app.app_context():
            db.create_all()
    else:
        db.create_all()
