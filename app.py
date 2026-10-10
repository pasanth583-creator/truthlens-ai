import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, redirect, url_for, abort, flash

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import config_by_name, Config
from database import db, Analysis, format_relative_time, init_db, delete_analysis, clear_history, get_analysis
from utils.validators import validate_input_text
from services.verification import verify_claim, synthesize_verification
from services.explainer import get_explainer
from services.evidence import WikipediaEvidenceProvider, GoogleFactCheckProvider, search_evidence
from services.google_fact_check import fact_check_article_claims, search_fact_checks, is_configured
from services.url_extractor import fetch_and_extract_article, validate_and_resolve_url

# Configure safe logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("truthlens.app")


def get_dashboard_metrics() -> dict:
    """Compute real database-backed statistics from SQLite persistence."""
    try:
        total_count = Analysis.query.count()
        reliable_count = Analysis.query.filter_by(predicted_label="Reliable").count()
        misleading_count = Analysis.query.filter_by(predicted_label="Misleading").count()
        false_count = Analysis.query.filter_by(predicted_label="False").count()
        conflict_count = Analysis.query.filter_by(conflict_detected=True).count()
        insufficient_count = Analysis.query.filter_by(evidence_status="insufficient").count()

        # Count analyses created today in UTC
        start_of_today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = Analysis.query.filter(Analysis.created_at >= start_of_today).count()

        # Average model confidence
        avg_conf_raw = db.session.query(db.func.avg(Analysis.confidence)).scalar()
        avg_confidence = round(float(avg_conf_raw), 4) if avg_conf_raw is not None else 0.0

        # Recent analyses
        recent_records = Analysis.query.order_by(Analysis.created_at.desc()).limit(10).all()
        recent_items = [rec.to_summary_dict() for rec in recent_records]

        return {
            "total_count": total_count,
            "reliable_count": reliable_count,
            "misleading_count": misleading_count,
            "false_count": false_count,
            "conflict_count": conflict_count,
            "insufficient_count": insufficient_count,
            "today_count": today_count,
            "average_confidence": avg_confidence,
            "average_confidence_pct": round(avg_confidence * 100, 1),
            "recent_analyses": recent_items
        }
    except Exception as e:
        logger.warning(f"Error computing dashboard metrics: {e}")
        return {
            "total_count": 0,
            "reliable_count": 0,
            "misleading_count": 0,
            "false_count": 0,
            "conflict_count": 0,
            "insufficient_count": 0,
            "today_count": 0,
            "average_confidence": 0.0,
            "average_confidence_pct": 0.0,
            "recent_analyses": []
        }


def create_app(config_name: str = "default") -> Flask:
    """Application factory for TruthLens AI Flask backend."""
    app = Flask(__name__)
    config_cls = config_by_name.get(config_name, Config)
    app.config.from_object(config_cls)

    # Initialize database
    try:
        db.init_app(app)
        init_db(app)
    except Exception as e:
        logger.warning(f"Database initialization encountered an error: {e}")

    # ==============================================================
    # WEB UI ROUTES
    # ==============================================================

    @app.route("/", methods=["GET"])
    def home():
        """Home page route displaying real database stats and core features."""
        stats = get_dashboard_metrics()
        return render_template("index.html", stats=stats)

    @app.route("/dashboard", methods=["GET"])
    def dashboard():
        """Real-time intelligence dashboard displaying actual SQLite data."""
        stats = get_dashboard_metrics()
        return render_template("dashboard.html", stats=stats)

    @app.route("/analyze", methods=["GET", "POST"])
    def analyze():
        """Analysis submission form and processor supporting Claim & News URL modes."""
        if request.method == "GET":
            mode = request.args.get("mode", "claim")
            return render_template("analyze.html", text="", url="", error=None, active_mode=mode)

        # POST submission
        mode = request.form.get("mode", "claim")

        # Mode: News URL Analysis
        if mode == "url":
            raw_url = request.form.get("url", "").strip()
            if not raw_url:
                return render_template(
                    "analyze.html",
                    text="",
                    url="",
                    error="Please provide a valid news article URL.",
                    error_code="EMPTY_URL",
                    active_mode="url",
                    fallback_eligible=False
                ), 400

            fetch_res = fetch_and_extract_article(raw_url, max_chars=app.config.get("MAX_INPUT_LENGTH", 10000))
            if not fetch_res.get("success"):
                return render_template(
                    "analyze.html",
                    text="",
                    url=raw_url,
                    error=fetch_res.get("error", "Failed to retrieve article content."),
                    error_code=fetch_res.get("error_code", "FETCH_FAILED"),
                    active_mode="url",
                    fallback_eligible=True
                ), 400

            extracted_text = fetch_res.get("content", "")
            article_title = fetch_res.get("title", "")
            source_url = fetch_res.get("url", raw_url)

            # Validate extracted content length
            is_valid, cleaned_text, err_msg = validate_input_text(
                extracted_text,
                min_length=app.config.get("MIN_INPUT_LENGTH", 5),
                max_length=app.config.get("MAX_INPUT_LENGTH", 10000)
            )
            if not is_valid:
                return render_template(
                    "analyze.html",
                    text="",
                    url=raw_url,
                    error=err_msg,
                    error_code="VALIDATION_FAILED",
                    active_mode="url",
                    fallback_eligible=True
                ), 400

            try:
                result = verify_claim(cleaned_text)
                record = Analysis(
                    input_text=cleaned_text,
                    predicted_label=result["prediction"]["label"],
                    confidence=float(result["prediction"]["confidence"]),
                    verification_status=result["verification"].get("status", "UNVERIFIED"),
                    evidence_status=result["evidence"].get("status", "insufficient"),
                    class_probabilities=result.get("probabilities", {}),
                    important_phrases=result["explanation"].get("important_phrases", []),
                    explanation_summary=result["explanation"].get("summary", ""),
                    evidence_summary=result["evidence"].get("summary", ""),
                    evidence_sources=result["evidence"].get("sources", []),
                    final_assessment=result["verification"].get("result", ""),
                    conflict_detected=bool(result["verification"].get("conflict_detected", False)),
                    source_url=source_url,
                    article_title=article_title
                )
                db.session.add(record)
                db.session.commit()
                return redirect(url_for("view_result", analysis_id=record.id))
            except Exception as exc:
                db.session.rollback()
                logger.error(f"URL analysis pipeline failure: {exc}", exc_info=True)
                return render_template(
                    "analyze.html",
                    text="",
                    url=raw_url,
                    error="An unexpected internal error occurred while processing the news article verification pipeline. Please try again.",
                    error_type="server_error",
                    error_code="INTERNAL_ERROR",
                    active_mode="url",
                    fallback_eligible=True
                ), 500

        # Mode: Direct Claim Text Analysis
        raw_text = request.form.get("text", "")
        is_valid, cleaned_text, err_msg = validate_input_text(
            raw_text,
            min_length=app.config.get("MIN_INPUT_LENGTH", 5),
            max_length=app.config.get("MAX_INPUT_LENGTH", 10000)
        )

        if not is_valid:
            return render_template("analyze.html", text=raw_text, url="", error=err_msg, error_type="validation", active_mode="claim"), 400

        try:
            # Execute full AI verification pipeline
            result = verify_claim(cleaned_text)

            # Persist record in database
            record = Analysis(
                input_text=cleaned_text,
                predicted_label=result["prediction"]["label"],
                confidence=float(result["prediction"]["confidence"]),
                verification_status=result["verification"].get("status", "UNVERIFIED"),
                evidence_status=result["evidence"].get("status", "insufficient"),
                class_probabilities=result.get("probabilities", {}),
                important_phrases=result["explanation"].get("important_phrases", []),
                explanation_summary=result["explanation"].get("summary", ""),
                evidence_summary=result["evidence"].get("summary", ""),
                evidence_sources=result["evidence"].get("sources", []),
                final_assessment=result["verification"].get("result", ""),
                conflict_detected=bool(result["verification"].get("conflict_detected", False))
            )
            db.session.add(record)
            db.session.commit()
            return redirect(url_for("view_result", analysis_id=record.id))

        except Exception as exc:
            db.session.rollback()
            logger.error(f"Analysis processing error: {exc}", exc_info=True)
            return render_template(
                "analyze.html",
                text=raw_text,
                url="",
                error="An unexpected internal error occurred while analyzing the claim. Please try again.",
                error_type="server_error",
                active_mode="claim"
            ), 500

    def _render_analysis_detail(analysis_id: Any):
        """Retrieve saved analysis record by ID from database and render result template."""
        try:
            record_id = int(analysis_id)
        except (ValueError, TypeError):
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Invalid analysis ID."}), 404
            return render_template("404.html", requested_id=str(analysis_id)), 404

        record = db.session.get(Analysis, record_id)
        if not record:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Analysis record not found."}), 404
            return render_template("404.html", requested_id=str(record_id)), 404

        analysis_data = record.to_dict()
        return render_template("result.html", analysis=analysis_data)

    # 1. Main History Listing Route
    @app.route("/history", methods=["GET"])
    def history():
        """List historical analysis runs in reverse chronological order."""
        records = Analysis.query.order_by(Analysis.created_at.desc()).all()
        history_items = [rec.to_summary_dict() for rec in records]
        return render_template("history.html", history_items=history_items)

    # 2. Clear All History Route (registered before parameterized /history/<id> routes)
    @app.route("/history/clear", methods=["GET", "POST", "DELETE"])
    def clear_all_history_records():
        """Safely clear all historical analysis records without modifying models or dropping tables."""
        if request.method == "GET":
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "GET method is not supported for clear history."}), 405
            flash("Direct GET requests cannot clear history. Please use the confirmation modal.", "warning")
            return redirect(url_for("history"))

        try:
            deleted_count = clear_history()
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({
                    "success": True,
                    "message": f"All analysis history cleared successfully ({deleted_count} records removed).",
                    "deleted_count": deleted_count
                }), 200
            flash(f"All analysis history records have been cleared ({deleted_count} removed).", "success")
            return redirect(url_for("history"))
        except Exception as exc:
            logger.error(f"Failed to clear analysis history: {exc}", exc_info=False)
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Internal error clearing analysis history."}), 500
            flash("An error occurred while clearing analysis history.", "error")
            return redirect(url_for("history"))

    # 3. Form-based and parameter-based Deletion Routes
    @app.route("/history/delete", methods=["GET", "POST", "DELETE"])
    @app.route("/history/<int:analysis_id>/delete", methods=["GET", "POST", "DELETE"])
    @app.route("/history/delete/<int:analysis_id>", methods=["GET", "POST", "DELETE"])
    @app.route("/history/<analysis_id>/delete", methods=["GET", "POST", "DELETE"])
    @app.route("/history/delete/<analysis_id>", methods=["GET", "POST", "DELETE"])
    def delete_history_item(analysis_id: Optional[Any] = None):
        """Safely delete a single historical analysis record without affecting other data."""
        if request.method == "GET":
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "GET method is not supported for deletion."}), 405
            flash("Direct GET requests cannot delete records. Please use the delete confirmation modal.", "warning")
            return redirect(url_for("history"))

        # Resolve record ID from URL parameter or POST body
        raw_id = analysis_id
        if raw_id is None:
            if request.is_json:
                raw_id = (request.get_json(silent=True) or {}).get("record_id")
            else:
                raw_id = request.form.get("record_id")

        if raw_id is None or str(raw_id).strip() == "":
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Missing record ID."}), 400
            flash("Missing analysis record ID for deletion.", "error")
            return redirect(url_for("history"))

        try:
            record_id = int(raw_id)
        except (ValueError, TypeError):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Invalid record ID."}), 400
            flash(f"Invalid record ID '{raw_id}'.", "error")
            return redirect(url_for("history"))

        try:
            deleted = delete_analysis(record_id)
        except Exception as exc:
            logger.error(f"Error deleting analysis record #{record_id}: {exc}", exc_info=False)
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Database error while deleting record."}), 500
            flash(f"Database error occurred while deleting record #{record_id}.", "error")
            return redirect(url_for("history"))

        if request.is_json or request.path.startswith("/api/"):
            if deleted:
                return jsonify({
                    "success": True,
                    "message": f"Analysis record #{record_id} deleted successfully.",
                    "deleted_id": record_id
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "error": f"Analysis record #{record_id} not found."
                }), 404

        if deleted:
            flash(f"Analysis record #{record_id} was successfully deleted.", "success")
        else:
            flash(f"Analysis record #{record_id} was not found in database.", "warning")
        return redirect(url_for("history"))

    # 4. Detail View Routes (typed int and string fallback)
    @app.route("/result/<int:analysis_id>", methods=["GET"])
    @app.route("/result/<analysis_id>", methods=["GET"])
    def view_result(analysis_id: Any):
        """View analysis report by id."""
        return _render_analysis_detail(analysis_id)

    @app.route("/history/<int:analysis_id>", methods=["GET"])
    @app.route("/history/<analysis_id>", methods=["GET"])
    def view_history_detail(analysis_id: Any):
        """View analysis report from history by id (consistent with /result/<id>)."""
        return _render_analysis_detail(analysis_id)

    @app.route("/refresh-evidence/<int:analysis_id>", methods=["POST"])
    @app.route("/refresh-evidence/<analysis_id>", methods=["POST"])
    def refresh_evidence_web(analysis_id: Any):
        """Web action to refresh live evidence for an existing analysis without retraining model."""
        try:
            record_id = int(analysis_id)
        except (ValueError, TypeError):
            abort(404)

        record = db.session.get(Analysis, record_id)
        if not record:
            abort(404)

        try:
            # Query live evidence bypassing cache
            new_evidence = search_evidence(record.input_text, bypass_cache=True)
            new_status = new_evidence.get("evidence_status", "insufficient")
            
            # Re-synthesize verification keeping model prediction intact
            synthesis = synthesize_verification(
                pred_label=record.predicted_label,
                confidence=record.confidence,
                evidence_status=new_status,
                confidence_threshold=app.config.get("EXPLANATION_CONFIDENCE_THRESHOLD", 0.60)
            )

            # Update evidence and verification fields only
            record.evidence_status = new_status
            record.evidence_summary = new_evidence.get("summary", "")
            record.evidence_sources = new_evidence.get("sources", [])
            record.verification_status = synthesis.get("status", "UNVERIFIED")
            record.final_assessment = synthesis.get("result", "")
            record.conflict_detected = bool(synthesis.get("conflict_detected", False))

            db.session.commit()
            return redirect(url_for("view_result", analysis_id=record.id))
        except Exception as err:
            db.session.rollback()
            logger.error(f"Live evidence refresh failed: {err}", exc_info=False)
            return redirect(url_for("view_result", analysis_id=record.id))

    @app.route("/about", methods=["GET"])
    def about():
        """System architecture and methodology about page."""
        return render_template("about.html")

    # ==============================================================
    # API ENDPOINTS
    # ==============================================================

    @app.route("/api/health", methods=["GET"])
    def api_health():
        """Health check endpoint."""
        model_loaded = False
        try:
            explainer = get_explainer()
            model_loaded = explainer.model is not None
        except Exception:
            model_loaded = False

        google_p = GoogleFactCheckProvider()
        provider_name = "Google Fact Check Tools API" if google_p.is_available() else "Wikipedia (Public API)"

        return jsonify({
            "status": "healthy",
            "model_loaded": model_loaded,
            "model": app.config.get("MODEL_NAME", "distilbert-base-uncased"),
            "classes": app.config.get("CLASSES", ["False", "Misleading", "Reliable"]),
            "evidence_provider": provider_name,
            "version": app.config.get("APP_VERSION", "1.0.0")
        }), 200

    @app.route("/api/dashboard", methods=["GET"])
    def api_dashboard():
        """Retrieve real database-derived metrics and recent verification activity."""
        metrics = get_dashboard_metrics()
        return jsonify({
            "success": True,
            "metrics": metrics
        }), 200

    @app.route("/api/analyze", methods=["POST"])
    def api_analyze():
        """REST API analysis endpoint accepting JSON payload."""
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Request body must be valid JSON with 'Content-Type: application/json'."
            }), 400

        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({
                "success": False,
                "error": "Invalid JSON body provided."
            }), 400

        raw_text = data.get("text")
        is_valid, cleaned_text, err_msg = validate_input_text(
            raw_text,
            min_length=app.config.get("MIN_INPUT_LENGTH", 5),
            max_length=app.config.get("MAX_INPUT_LENGTH", 10000)
        )

        if not is_valid:
            status_code = 413 if "exceeds" in (err_msg or "") else 400
            return jsonify({
                "success": False,
                "error": err_msg
            }), status_code

        try:
            result = verify_claim(cleaned_text)

            # Persist record in database
            record = Analysis(
                input_text=cleaned_text,
                predicted_label=result["prediction"]["label"],
                confidence=float(result["prediction"]["confidence"]),
                verification_status=result["verification"].get("status", "UNVERIFIED"),
                evidence_status=result["evidence"].get("status", "insufficient"),
                class_probabilities=result.get("probabilities", {}),
                important_phrases=result["explanation"].get("important_phrases", []),
                explanation_summary=result["explanation"].get("summary", ""),
                evidence_summary=result["evidence"].get("summary", ""),
                evidence_sources=result["evidence"].get("sources", []),
                final_assessment=result["verification"].get("result", ""),
                conflict_detected=bool(result["verification"].get("conflict_detected", False))
            )
            db.session.add(record)
            db.session.commit()

            return jsonify({
                "success": True,
                "analysis_id": record.id,
                "analysis": result,
                "data": result
            }), 200
        except Exception as exc:
            db.session.rollback()
            logger.error(f"API processing failure: {exc}", exc_info=False)
            return jsonify({
                "success": False,
                "error": "An internal error occurred during claim verification. Please try again."
            }), 500

    @app.route("/api/analyze-url", methods=["POST"])
    def api_analyze_url():
        """REST API endpoint for verifying public news article URLs with SSRF safety."""
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Request body must be valid JSON with 'Content-Type: application/json'."
            }), 400

        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({
                "success": False,
                "error": "Invalid JSON body provided."
            }), 400

        raw_url = data.get("url")
        if not raw_url or not isinstance(raw_url, str):
            return jsonify({
                "success": False,
                "error": "Field 'url' is required and must be a valid string."
            }), 400

        fetch_res = fetch_and_extract_article(raw_url, max_chars=app.config.get("MAX_INPUT_LENGTH", 10000))
        if not fetch_res.get("success"):
            return jsonify({
                "success": False,
                "overall_status": "failed",
                "article_fetch_status": "failed",
                "error": fetch_res.get("error", "Failed to retrieve article content."),
                "error_code": fetch_res.get("error_code", "FETCH_FAILED"),
                "url": raw_url,
                "is_homepage": bool(fetch_res.get("is_homepage", False))
            }), 400

        extracted_text = fetch_res.get("content", "")
        article_title = fetch_res.get("title", "")
        source_url = fetch_res.get("url", raw_url)

        is_valid, cleaned_text, err_msg = validate_input_text(
            extracted_text,
            min_length=app.config.get("MIN_INPUT_LENGTH", 5),
            max_length=app.config.get("MAX_INPUT_LENGTH", 10000)
        )
        if not is_valid:
            return jsonify({
                "success": False,
                "overall_status": "failed",
                "article_fetch_status": "success",
                "error": err_msg,
                "error_code": "VALIDATION_FAILED",
                "url": raw_url
            }), 400

        try:
            result = verify_claim(cleaned_text)
            record = Analysis(
                input_text=cleaned_text,
                predicted_label=result["prediction"]["label"],
                confidence=float(result["prediction"]["confidence"]),
                verification_status=result["verification"].get("status", "UNVERIFIED"),
                evidence_status=result["evidence"].get("status", "insufficient"),
                class_probabilities=result.get("probabilities", {}),
                important_phrases=result["explanation"].get("important_phrases", []),
                explanation_summary=result["explanation"].get("summary", ""),
                evidence_summary=result["evidence"].get("summary", ""),
                evidence_sources=result["evidence"].get("sources", []),
                final_assessment=result["verification"].get("result", ""),
                conflict_detected=bool(result["verification"].get("conflict_detected", False)),
                source_url=source_url,
                article_title=article_title
            )
            db.session.add(record)
            db.session.commit()

            return jsonify({
                "success": True,
                "overall_status": "completed",
                "article_fetch_status": "success",
                "analysis_id": record.id,
                "article_title": article_title,
                "source_url": source_url,
                "canonical_url": fetch_res.get("canonical_url", source_url),
                "domain": fetch_res.get("domain", ""),
                "author": fetch_res.get("author", ""),
                "publish_date": fetch_res.get("publish_date", ""),
                "word_count": fetch_res.get("word_count", len(cleaned_text.split())),
                "extracted_claims": [result.get("claim", "")],
                "prediction": result.get("prediction"),
                "verification": result.get("verification"),
                "evidence": result.get("evidence"),
                "analysis": result,
                "data": result
            }), 200
        except Exception as exc:
            db.session.rollback()
            logger.error(f"API URL analysis processing error: {exc}", exc_info=False)
            return jsonify({
                "success": False,
                "overall_status": "failed",
                "error": "An internal error occurred during article verification. Please try again.",
                "error_code": "INTERNAL_ERROR"
            }), 500

    @app.route("/api/refresh-evidence/<analysis_id>", methods=["POST"])
    def api_refresh_evidence(analysis_id: str):
        """API endpoint to refresh live evidence for an analysis record without recomputing model predictions."""
        try:
            record_id = int(analysis_id)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid analysis ID."}), 404

        record = db.session.get(Analysis, record_id)
        if not record:
            return jsonify({"success": False, "error": "Analysis record not found."}), 404

        try:
            new_evidence = search_evidence(record.input_text, bypass_cache=True)
            new_status = new_evidence.get("evidence_status", "insufficient")
            
            synthesis = synthesize_verification(
                pred_label=record.predicted_label,
                confidence=record.confidence,
                evidence_status=new_status,
                confidence_threshold=app.config.get("EXPLANATION_CONFIDENCE_THRESHOLD", 0.60)
            )

            record.evidence_status = new_status
            record.evidence_summary = new_evidence.get("summary", "")
            record.evidence_sources = new_evidence.get("sources", [])
            record.verification_status = synthesis.get("status", "UNVERIFIED")
            record.final_assessment = synthesis.get("result", "")
            record.conflict_detected = bool(synthesis.get("conflict_detected", False))

            db.session.commit()

            return jsonify({
                "success": True,
                "analysis_id": record.id,
                "evidence": new_evidence,
                "verification": synthesis
            }), 200
        except Exception as err:
            db.session.rollback()
            logger.error(f"API evidence refresh failure: {err}", exc_info=False)
            return jsonify({"success": False, "error": "Failed to refresh live evidence."}), 500

    @app.route("/api/fact-check", methods=["POST"])
    def api_fact_check():
        """Search Google Fact Check Tools API across extracted factual claims from submitted text."""
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            raw_text = payload.get("text", "")
        else:
            raw_text = request.form.get("text", "")

        if not raw_text or not raw_text.strip():
            return jsonify({
                "status": "error",
                "message": "Field 'text' is required and cannot be empty.",
                "claims": []
            }), 400

        is_valid, cleaned_text, err_msg = validate_input_text(
            raw_text,
            min_length=app.config.get("MIN_INPUT_LENGTH", 5),
            max_length=app.config.get("MAX_INPUT_LENGTH", 10000)
        )
        if not is_valid:
            return jsonify({
                "status": "error",
                "message": err_msg,
                "claims": []
            }), 400

        try:
            fact_check_res = fact_check_article_claims(cleaned_text)
            return jsonify(fact_check_res), 200
        except Exception as exc:
            logger.error(f"Google Fact Check API route error: {exc}", exc_info=False)
            return jsonify({
                "status": "error",
                "message": "An error occurred while communicating with Google Fact Check Tools API.",
                "claims": []
            }), 500

    @app.route("/api/history/<analysis_id>", methods=["DELETE", "POST"])
    def api_delete_history(analysis_id: str):
        """API endpoint to delete a specific analysis record."""
        return delete_history_item(analysis_id)

    @app.route("/api/history/clear", methods=["POST", "DELETE"])
    def api_clear_history():
        """API endpoint to clear all history records."""
        return clear_all_history_records()

    # Custom HTTP error handlers
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Requested API resource not found."}), 404
        return render_template("404.html", requested_id=None), 404

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Internal server error."}), 500
        return "<h1>500 Server Error</h1><p>An unexpected error occurred.</p>", 500

    return app


# Application entry point
app = create_app(os.getenv("FLASK_ENV", "default"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

