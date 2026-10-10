import sys
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.claim_extractor import extract_claim
from services.explainer import explain_prediction, EXPLANATION_CONFIDENCE_THRESHOLD
from services.evidence import search_evidence
from services.google_fact_check import fact_check_article_claims


def synthesize_verification(
    pred_label: str,
    confidence: float,
    evidence_status: str,
    confidence_threshold: float = EXPLANATION_CONFIDENCE_THRESHOLD
) -> Dict[str, Any]:
    """Combine model prediction and evidence verification signals into a coherent assessment.
    
    Evidence-First Decision Matrix:
      - Insufficient evidence -> UNVERIFIED / INSUFFICIENT EVIDENCE (never force True or False)
      - Mixed evidence -> MISLEADING (disputed / contested findings)
      - False/Misleading + Contradicting -> Likely False / Potentially False (if low confidence)
      - Reliable + Supporting -> Supported / Provisionally Supported (if low confidence)
      - False/Misleading + Supporting -> CONFLICTING SIGNALS
      - Reliable + Contradicting -> CONFLICTING SIGNALS
    """
    is_low_confidence = confidence < confidence_threshold
    conflict_detected = False

    # Case 1: Insufficient Evidence
    if evidence_status == "insufficient":
        status = "UNVERIFIED"
        result = "Unverified / Insufficient Evidence -- external evidence is insufficient to conclusively verify this claim."
        explanation_note = (
            "The model evaluated linguistic style, but authoritative external sources "
            "do not provide adequate evidence to support or refute the assertion. The claim remains unverified."
        )

    # Case 2: Mixed / Contested Evidence
    elif evidence_status == "mixed":
        status = "MISLEADING"
        result = "Misleading / Mixed Evidence -- retrieved external sources report contested or conflicting findings."
        explanation_note = (
            "Available external evidence presents differing or contested perspectives, suggesting the claim "
            "may oversimplify, misattribute, or present contested points as settled fact."
        )

    # Case 3: False or Misleading + Contradicting Evidence
    elif pred_label in {"False", "Misleading"} and evidence_status == "contradicting":
        status = "LIKELY_FALSE"
        if is_low_confidence:
            result = "Potentially False -- retrieved evidence contradicts the claim, but model confidence is low."
        else:
            result = "Likely False -- retrieved evidence contradicts the claim."
        explanation_note = (
            "Both the classifier's pattern recognition and external authoritative records "
            "indicate that this statement is false, disproven, or misleading."
        )

    # Case 4: False or Misleading + Supporting Evidence (CONFLICT)
    elif pred_label in {"False", "Misleading"} and evidence_status == "supporting":
        conflict_detected = True
        status = "CONFLICTING_SIGNALS"
        result = (
            f"Conflicting Signals -- model predicts {pred_label}, but retrieved authoritative evidence supports the claim."
        )
        explanation_note = (
            f"The neural classifier associated the input text with {pred_label} patterns (possibly due to sensational "
            "or controversial wording), but external factual evidence affirmatively corroborates the statement. "
            "External evidence should take precedence over surface stylistic classification."
        )

    # Case 5: Reliable + Supporting Evidence
    elif pred_label == "Reliable" and evidence_status == "supporting":
        status = "SUPPORTED"
        if is_low_confidence:
            result = "Provisionally Supported -- retrieved evidence corroborates the claim, though model confidence is low."
        else:
            result = "Supported -- model predicts Reliable and retrieved external evidence corroborates the claim."
        explanation_note = (
            "The classifier detected credible linguistic structure, and external authoritative "
            "records affirmatively document and corroborate the core assertion."
        )

    # Case 6: Reliable + Contradicting Evidence (CONFLICT)
    elif pred_label == "Reliable" and evidence_status == "contradicting":
        conflict_detected = True
        status = "CONFLICTING_SIGNALS"
        result = (
            "Conflicting Signals -- model predicts Reliable, but retrieved external evidence contradicts the claim."
        )
        explanation_note = (
            "The input phrasing appears measured, formal, or authoritative, leading the classifier to predict "
            "Reliable. However, factual external evidence directly refutes the claim. Surface credibility does not "
            "substitute for factual truth."
        )

    # Fallback / Default
    else:
        status = "UNVERIFIED"
        result = f"Unverified -- model predicted {pred_label}, but evidence remains inconclusive."
        explanation_note = "Available evidence does not adequately establish either side."

    return {
        "status": status,
        "result": result,
        "conflict_detected": conflict_detected,
        "assessment_note": explanation_note,
        "is_low_confidence": is_low_confidence
    }


def verify_claim(text: str, confidence_threshold: float = EXPLANATION_CONFIDENCE_THRESHOLD) -> Dict[str, Any]:
    """Execute end-to-end verification pipeline: claim extraction, prediction, explainability, and live evidence retrieval."""
    if not text or not text.strip():
        return {
            "claim": "",
            "prediction": {"label": "Reliable", "confidence": 0.3333},
            "probabilities": {"False": 0.3333, "Misleading": 0.3333, "Reliable": 0.3334},
            "explanation": {
                "summary": "Input text was empty.",
                "confidence_status": "Low confidence",
                "important_phrases": []
            },
            "evidence": {
                "status": "insufficient",
                "summary": "No input text provided.",
                "sources": [],
                "supporting_count": 0,
                "contradicting_count": 0,
                "neutral_count": 0,
                "provider": "Wikipedia (Public API)"
            },
            "verification": {
                "status": "UNVERIFIED",
                "result": "Unverified / Insufficient Evidence — input text was empty.",
                "conflict_detected": False,
                "assessment_note": "No text provided for analysis.",
                "is_low_confidence": True
            },
            "responsible_ai": {
                "confidence_note": "Model confidence is not factual certainty.",
                "verification_note": "Evidence retrieval is separate from the classifier prediction. When evidence is insufficient, the claim remains unverified."
            }
        }

    # 1. Claim extraction
    extracted = extract_claim(text)
    clean_claim = extracted["claim"]

    # 2. Model prediction & explainability (DistilBERT static weights)
    explanation_res = explain_prediction(text, confidence_threshold=confidence_threshold)
    pred = explanation_res["prediction"]
    probs = explanation_res["probabilities"]
    exp = explanation_res["explanation"]

    # 3. Live Evidence retrieval & quality ranking (MediaWiki + Google Fact Check)
    try:
        evidence_res = search_evidence(text)
    except Exception:
        from datetime import datetime, timezone
        now_dt = datetime.now(timezone.utc)
        evidence_res = {
            "claim": clean_claim,
            "extracted_claims": [],
            "evidence_status": "insufficient",
            "summary": "External evidence retrieval was unavailable or encountered an error. Claim remains unverified.",
            "sources": [],
            "supporting_count": 0,
            "contradicting_count": 0,
            "neutral_count": 0,
            "total_retrieved": 0,
            "search_queries": [],
            "retrieved_at": now_dt.isoformat(),
            "retrieved_at_display": now_dt.strftime("%d %b %Y, %H:%M UTC"),
            "provider": "Wikipedia (Public API)",
            "provider_status": {
                "wikipedia": {"status": "ERROR", "status_display": "ERROR — REQUEST FAILED"},
                "google_fact_check": {"status": "UNAVAILABLE", "status_display": "UNAVAILABLE — NOT CONFIGURED"}
            },
            "status": "UNAVAILABLE"
        }
    ev_status = evidence_res["evidence_status"]
    ev_summary = evidence_res["summary"]
    ev_sources = evidence_res["sources"]

    # 4. Google Fact Check Tools API query
    try:
        fact_checks = fact_check_article_claims(text)
    except Exception:
        fact_checks = {
            "status": "error",
            "provider_status": "ERROR",
            "status_display": "ERROR — REQUEST FAILED",
            "message": "Error communicating with Google Fact Check API.",
            "claims": [],
            "matched_claims": 0,
            "queries_used": []
        }

    # 5. Synthesize verification decision
    verification_synthesis = synthesize_verification(
        pred_label=pred["label"],
        confidence=pred["confidence"],
        evidence_status=ev_status,
        confidence_threshold=confidence_threshold
    )

    return {
        "claim": clean_claim,
        "original_text": text,
        "search_query": extracted["search_query"],
        "search_queries": evidence_res.get("search_queries", extracted.get("search_queries", [])),
        "entities": extracted.get("entities", []),
        "extracted_claims": evidence_res.get("extracted_claims", []),
        "prediction": pred,
        "probabilities": probs,
        "explanation": exp,
        "evidence": {
            "status": ev_status,
            "summary": ev_summary,
            "sources": ev_sources,
            "supporting_count": evidence_res.get("supporting_count", 0),
            "contradicting_count": evidence_res.get("contradicting_count", 0),
            "neutral_count": evidence_res.get("neutral_count", 0),
            "total_retrieved": evidence_res.get("total_retrieved", len(ev_sources)),
            "provider": evidence_res.get("provider", "Wikipedia (Public API)"),
            "provider_status": evidence_res.get("provider_status", {}),
            "search_queries": evidence_res.get("search_queries", []),
            "retrieved_at": evidence_res.get("retrieved_at", ""),
            "retrieved_at_display": evidence_res.get("retrieved_at_display", "")
        },
        "fact_checks": fact_checks,
        "verification": verification_synthesis,
        "responsible_ai": {
            "confidence_note": "Model confidence is not factual certainty.",
            "verification_note": (
                "Evidence retrieval is separate from the classifier prediction. "
                "When evidence is insufficient, the claim remains unverified."
            )
        }
    }


if __name__ == "__main__":
    sample = "George Washington was the first President of the United States."
    print("Testing verify_claim:")
    output = verify_claim(sample)
    print(f"Prediction: {output['prediction']}")
    print(f"Evidence Status: {output['evidence']['status']}")
    print(f"Verdict: {output['verification']['result']}")
