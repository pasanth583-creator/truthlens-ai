from typing import Dict, Any


def generate_verification_report(result: Dict[str, Any]) -> str:
    """Generate a clean, structured, human-readable TruthLens AI verification report."""
    claim = result.get("claim", "")
    pred = result.get("prediction", {})
    label = pred.get("label", "Unknown")
    confidence = pred.get("confidence", 0.0)

    probabilities = result.get("probabilities", {})
    prob_lines = []
    for cls in ["False", "Misleading", "Reliable"]:
        val = probabilities.get(cls, 0.0)
        prob_lines.append(f"{cls}: {val * 100:.1f}%")
    prob_str = "\n".join(prob_lines)

    explanation = result.get("explanation", {})
    phrases = explanation.get("important_phrases", [])
    phrase_lines = []
    if phrases:
        for p in phrases:
            phrase_lines.append(f"* \"{p['phrase']}\" ({p['direction']}, rel. weight: {p['importance']:.2f})")
    else:
        phrase_lines.append("* (No strong influential phrases isolated)")
    phrases_str = "\n".join(phrase_lines)

    evidence = result.get("evidence", {})
    ev_status = evidence.get("status", "insufficient").upper()
    ev_summary = evidence.get("summary", "No evidence summary available.")
    sources = evidence.get("sources", [])

    source_blocks = []
    if sources:
        for idx, s in enumerate(sources, 1):
            source_blocks.append(
                f"{idx}. {s.get('title', 'Unknown Title')}\n"
                f"   Source:    {s.get('source', 'Unknown')}\n"
                f"   URL:       {s.get('url', 'N/A')}\n"
                f"   Relation:  {s.get('relation', 'neutral').upper()}\n"
                f"   Relevance: {s.get('relevance_score', 0.0):.2f}"
            )
    else:
        source_blocks.append("(No external sources found or evidence was insufficient -- zero placeholder URLs)")
    sources_str = "\n\n".join(source_blocks)

    verification = result.get("verification", {})
    assessment = verification.get("result", "Unverified")
    conflict = verification.get("conflict_detected", False)
    status_tag = verification.get("status", "UNVERIFIED")

    conflict_banner = ""
    if conflict:
        conflict_banner = (
            "\n"
            "************************************************************\n"
            "[!] ALERT: CONFLICTING SIGNALS DETECTED\n"
            f"   The model predicted [{label}], but retrieved external evidence\n"
            f"   indicates [{ev_status}]. External facts supersede classifier patterns.\n"
            "************************************************************\n"
        )

    report_lines = [
        "----------------------------------------",
        "TRUTHLENS AI VERIFICATION REPORT",
        "----------------------------------------",
        "",
        "CLAIM",
        f"\"{claim}\"",
        "",
        "AI PREDICTION",
        f"{label}",
        "",
        "MODEL CONFIDENCE",
        f"{confidence * 100:.1f}% ({explanation.get('confidence_status', 'Model prediction')})",
        "",
        "CLASS PROBABILITIES",
        prob_str,
        "",
        "WHY THE MODEL PREDICTED THIS",
        "Important phrases:",
        phrases_str,
        "",
        "EVIDENCE VERIFICATION",
        f"Status:\n{ev_status}",
        "",
        "Evidence summary:",
        ev_summary,
        "",
        "SOURCES",
        sources_str,
        "",
        "FINAL ASSESSMENT",
        assessment,
    ]

    if conflict_banner:
        report_lines.append(conflict_banner)

    report_lines.extend([
        "",
        "RESPONSIBLE AI NOTE",
        "Model confidence is not factual certainty.",
        "Evidence retrieval is separate from the classifier prediction.",
        "When evidence is insufficient, the claim remains unverified.",
        "----------------------------------------"
    ])

    return "\n".join(report_lines)
