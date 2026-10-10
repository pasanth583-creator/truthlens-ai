# database.py
"""SQLAlchemy database models and initialization for TruthLens AI.
Handles persistence of analysis requests, predictions, explainability tokens,
and external verification results.
"""
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from flask_sqlalchemy import SQLAlchemy

# SQLAlchemy instance - initialized in app.py
db = SQLAlchemy()


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def format_relative_time(dt: Optional[datetime]) -> str:
    """Compute human-friendly relative time from real timezone-aware UTC datetime."""
    if not dt:
        return "Unknown"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff_seconds = max(0, int((now - dt).total_seconds()))
    if diff_seconds < 15:
        return "Just now"
    if diff_seconds < 60:
        return f"{diff_seconds} seconds ago"
    minutes = diff_seconds // 60
    if minutes == 1:
        return "1 minute ago"
    if minutes < 60:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours == 1:
        return "1 hour ago"
    if hours < 24:
        return f"{hours} hours ago"
    days = hours // 24
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


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

    # News URL analysis metadata
    source_url = db.Column(db.String(1000), nullable=True)
    article_title = db.Column(db.String(500), nullable=True)

    def __init__(
        self,
        input_text: str = "",
        predicted_label: str = "",
        confidence: float = 0.0,
        verification_status: str = "UNVERIFIED",
        evidence_status: str = "insufficient",
        class_probabilities: Optional[Dict[str, Any]] = None,
        important_phrases: Optional[Any] = None,
        explanation_summary: Optional[str] = None,
        evidence_summary: Optional[str] = None,
        evidence_sources: Optional[Any] = None,
        final_assessment: Optional[str] = None,
        conflict_detected: bool = False,
        source_url: Optional[str] = None,
        article_title: Optional[str] = None,
        **kwargs: Any
    ):
        self.input_text = input_text
        self.predicted_label = predicted_label
        self.confidence = confidence
        self.verification_status = verification_status
        self.evidence_status = evidence_status
        self.class_probabilities = class_probabilities if class_probabilities is not None else {}
        self.important_phrases = important_phrases
        self.explanation_summary = explanation_summary
        self.evidence_summary = evidence_summary
        self.evidence_sources = evidence_sources
        self.final_assessment = final_assessment
        self.conflict_detected = conflict_detected
        self.source_url = source_url
        self.article_title = article_title
        for k, v in kwargs.items():
            setattr(self, k, v)

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
                        "url": str(s.get("url", "#")),
                        "retrieved_at": str(s.get("retrieved_at", "")),
                        "retrieved_at_display": str(s.get("retrieved_at_display", "")),
                        "status": str(s.get("status", "RETRIEVED"))
                    })

        # Count stances dynamically from sources
        supp_count = sum(1 for s in sources if str(s.get("relation", "")).lower() == "supports")
        contra_count = sum(1 for s in sources if str(s.get("relation", "")).lower() in ("contradicts", "refutes"))
        neut_count = sum(1 for s in sources if str(s.get("relation", "")).lower() in ("neutral", "unspecified"))

        # Extract unique queries used across sources
        queries_used = list(dict.fromkeys([s.get("query_used") for s in sources if s.get("query_used")]))

        # Format created_at nicely
        created_str = ""
        created_relative = ""
        if self.created_at:
            try:
                created_str = self.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                created_relative = format_relative_time(self.created_at)
            except Exception:
                created_str = str(self.created_at)

        conf_val = 0.0
        try:
            conf_val = float(self.confidence)
        except (TypeError, ValueError):
            conf_val = 0.0

        conf_status = "Model prediction" if conf_val >= 0.60 else "Low confidence"

        # Evidence provider name
        has_wiki = any(s.get("source") == "Wikipedia" for s in sources)
        provider_name = "Wikipedia (Public API)" if has_wiki or not sources else (sources[0].get("source") or "Wikipedia (Public API)")

        return {
            "id": self.id,
            "claim": self.input_text or "",
            "created_at": created_str,
            "created_at_relative": created_relative,
            "source_url": self.source_url,
            "article_title": self.article_title,
            "search_queries": queries_used,
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
                "sources": sources,
                "supporting_count": supp_count,
                "contradicting_count": contra_count,
                "neutral_count": neut_count,
                "total_retrieved": len(sources),
                "provider": provider_name,
                "search_queries": queries_used
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
        """Return a compact summary suitable for history and dashboard list views."""
        text = self.input_text or ""
        shortened_claim = text[:90] + ("..." if len(text) > 90 else "")
        created_str = ""
        created_relative = ""
        if self.created_at:
            try:
                created_str = self.created_at.strftime("%Y-%m-%d %H:%M UTC")
                created_relative = format_relative_time(self.created_at)
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
            "created_at_relative": created_relative,
            "claim_short": shortened_claim,
            "claim_full": text,
            "predicted_label": self.predicted_label or "Unknown",
            "confidence": round(conf_val, 4),
            "verification_status": self.verification_status or "UNVERIFIED",
            "evidence_status": self.evidence_status or "insufficient",
            "conflict_detected": bool(self.conflict_detected),
            "source_url": self.source_url,
            "article_title": self.article_title
        }


def get_analysis(analysis_id: int) -> Optional[Analysis]:
    """Retrieve a single Analysis record by primary key."""
    try:
        return db.session.get(Analysis, int(analysis_id))
    except (ValueError, TypeError):
        return None


def delete_analysis(analysis_id: int) -> bool:
    """Safely delete a single Analysis record by primary key.
    
    Returns True if found and deleted, False otherwise.
    Rolls back automatically on failure.
    """
    try:
        rec_id = int(analysis_id)
    except (ValueError, TypeError):
        return False

    record = db.session.get(Analysis, rec_id)
    if not record:
        return False

    try:
        db.session.delete(record)
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        raise exc


def clear_history() -> int:
    """Safely delete all Analysis records without dropping or altering database tables.
    
    Returns the number of deleted records.
    Rolls back automatically on failure.
    """
    try:
        # Count and delete rows cleanly
        deleted_count = db.session.query(Analysis).delete()
        db.session.commit()
        return int(deleted_count)
    except Exception as exc:
        db.session.rollback()
        raise exc


def init_db(app=None):
    """Create tables if they do not exist and ensure schema migrations."""
    def _migrate():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                res = conn.execute(db.text("PRAGMA table_info(analysis)")).fetchall()
                cols = {r[1] for r in res}
                if "source_url" not in cols:
                    conn.execute(db.text("ALTER TABLE analysis ADD COLUMN source_url VARCHAR(1000)"))
                if "article_title" not in cols:
                    conn.execute(db.text("ALTER TABLE analysis ADD COLUMN article_title VARCHAR(500)"))
                conn.commit()
        except Exception:
            pass

    if app:
        with app.app_context():
            _migrate()
    else:
        _migrate()

