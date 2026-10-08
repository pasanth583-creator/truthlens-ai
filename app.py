import os
import sys
import json
import logging
from pathlib import Path
from flask import Flask, request, jsonify, render_template, redirect, url_for, abort

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import config_by_name, Config
from database import db, Analysis
from utils.validators import validate_input_text
from services.verification import verify_claim
from services.explainer import get_explainer
from services.evidence import WikipediaEvidenceProvider, GoogleFactCheckProvider

# Configure safe logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("truthlens.app")


def create_app(config_name: str = "default") -> Flask:
    """Application factory for TruthLens AI Flask backend."""
    app = Flask(__name__)
    config_cls = config_by_name.get(config_name, Config)
    app.config.from_object(config_cls)

    # Initialize database
    try:
        db.init_app(app)
        with app.app_context():
            db.create_all()
    except Exception as e:
        logger.warning(f"Database initialization encountered an error: {e}")

    # ==============================================================
    # WEB UI ROUTES
    # ==============================================================

    @app.route("/", methods=["GET"])
    def home():
        """Home page route."""
        return render_template("index.html")

    @app.route("/analyze", methods=["GET", "POST"])
    def analyze():
        """Analysis submission form and processor."""
        if request.method == "GET":
            return render_template("analyze.html", text="", error=None)

        # POST submission
        raw_text = request.form.get("text", "")
        is_valid, cleaned_text, err_msg = validate_input_text(
            raw_text,
            min_length=app.config.get("MIN_INPUT_LENGTH", 5),
            max_length=app.config.get("MAX_INPUT_LENGTH", 10000)
        )

        if not is_valid:
            return render_template("analyze.html", text=raw_text, error=err_msg), 400

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
            logger.error(f"Analysis processing error: {exc}", exc_info=False)
            return render_template(
                "analyze.html",
                text=raw_text,
                error="An unexpected internal error occurred while analyzing the claim. Please try again."
            ), 500

    def _render_analysis_detail(analysis_id: str):
        """Retrieve saved analysis record by ID from database and render result template."""
        try:
            record_id = int(analysis_id)
        except (ValueError, TypeError):
            abort(404)

        record = db.session.get(Analysis, record_id)
        if not record:
            abort(404)

        analysis_data = record.to_dict()
        return render_template("result.html", analysis=analysis_data)

    @app.route("/result/<analysis_id>", methods=["GET"])
    def view_result(analysis_id: str):
        """View analysis report by id."""
        return _render_analysis_detail(analysis_id)

    @app.route("/history/<analysis_id>", methods=["GET"])
    def view_history_detail(analysis_id: str):
        """View analysis report from history by id (consistent with /result/<id>)."""
        return _render_analysis_detail(analysis_id)

    @app.route("/history", methods=["GET"])
    def history():
        """List historical analysis runs in reverse chronological order."""
        records = Analysis.query.order_by(Analysis.created_at.desc()).all()
        history_items = [rec.to_summary_dict() for rec in records]
        return render_template("history.html", history_items=history_items)

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
        # Check if explainer model is loaded or accessible
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

    # Custom HTTP error handlers
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Requested API resource not found."}), 404
        return "<h1>404 Not Found</h1><p>The requested page or analysis record does not exist.</p>", 404

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
