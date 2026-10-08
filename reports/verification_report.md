# TruthLens AI — Phase 8 Verification Report Engine Documentation

## 1. Architecture Overview
TruthLens AI unifies modern Transformer NLP with live open-web evidence verification while enforcing strict epistemological boundaries between linguistic prediction and factual verification.

```
                        [User Claim / Article]
                                   │
               ┌───────────────────┴───────────────────┐
               ▼                                       ▼
    [Phase 6 Explainer Engine]              [Phase 7 Evidence Engine]
    - DistilBERT 3-Way Classifier           - Claim Extraction
    - Softmax Class Probabilities           - Modular Search (Wikipedia API)
    - Integrated Gradients Attribution      - Content Relevance Ranking
               │                                       │
               │ (Prediction Signal)                   │ (Verification Signal)
               └───────────────────┬───────────────────┘
                                   ▼
                   [Phase 8 Verification Service]
                   - Decision Matrix Synthesis
                   - Conflict Detection Banner
                   - Low-Confidence Qualifying
                   - Human-Readable Report Formatter
```

---

## 2. Prediction vs. Evidence Separation
- **Model Prediction**: Reflects stylistic, lexical, and discourse patterns learned from the labeled corpus during supervised training. High confidence indicates stylistic conformity, not factual truth.
- **Evidence Verification**: Reflects empirical corroboration or contradiction from external authoritative records.
- **Independence Principle**: TruthLens AI never overrides external evidence with a model prediction, nor does it force a model to change its internal class probability because of missing evidence.

---

## 3. Verification Decision Matrix

| Model Prediction | Model Confidence | Evidence Status | Final Verification Assessment | Internal Status |
|---|---|---|---|---|
| **False / Misleading** | High ($\ge 60\%$) | **Contradicting** | *"Likely False — retrieved evidence contradicts the claim."* | `LIKELY_FALSE` |
| **False / Misleading** | Low ($< 60\%$) | **Contradicting** | *"Potentially False — retrieved evidence contradicts the claim, but model confidence is low."* | `LIKELY_FALSE` |
| **Reliable** | High ($\ge 60\%$) | **Supporting** | *"Supported — model predicts Reliable and retrieved external evidence corroborates the claim."* | `SUPPORTED` |
| **Reliable** | Low ($< 60\%$) | **Supporting** | *"Provisionally Supported — retrieved evidence corroborates the claim, though model confidence is low."* | `SUPPORTED` |
| **False / Misleading** | Any | **Supporting** | **CONFLICTING SIGNALS**: *"Model predicts False/Misleading, but external evidence supports the claim."* | `CONFLICTING_SIGNALS` |
| **Reliable** | Any | **Contradicting** | **CONFLICTING SIGNALS**: *"Model predicts Reliable, but external evidence contradicts the claim."* | `CONFLICTING_SIGNALS` |
| **Any** | Any | **Insufficient** | **UNVERIFIED**: *"Insufficient reliable evidence was retrieved to verify this claim."* | `UNVERIFIED` |

---

## 4. Confidence Handling
- **Threshold**: Configured via `EXPLANATION_CONFIDENCE_THRESHOLD = 0.60` (60.0%).
- **Qualification**: When confidence $< 0.60$, the output is explicitly labeled as *"Low model confidence"*, and final verdicts are toned down (e.g. from "Likely False" to "Potentially False").

---

## 5, 6, 7. Evidence Signal Handling

### Supporting Evidence
- Triggered when authoritative sources affirmatively document the assertion.
- If aligned with a `Reliable` classification, the assessment is `Supported`.

### Contradicting Evidence
- Triggered when authoritative sources directly refute, debunk, or negate the claim.
- If aligned with `False` or `Misleading`, the assessment is `Likely False`.

### Insufficient Evidence
- Triggered when external sources are absent, ambiguous, or below relevance thresholds ($< 0.35$).
- **Crucial Rule**: The claim is marked as **`UNVERIFIED`**. The system **never** outputs "True" or "False" when evidence is lacking.

---

## 8. Conflicting Signals Handling
When the neural classifier and retrieved external evidence disagree, TruthLens AI displays a prominent conflict banner:
```
************************************************************
[!] ALERT: CONFLICTING SIGNALS DETECTED
    The model predicted [Misleading], but retrieved external evidence
    indicates [SUPPORTING]. External facts supersede classifier patterns.
************************************************************
```
This is a critical responsible-AI safety mechanism that prevents deceptive language (e.g., formal prose used to wrap a falsehood, or aggressive political soundbites stating a factual truth) from misleading the user.

---

## 9. Example Human-Readable Verification Report

```
----------------------------------------
TRUTHLENS AI VERIFICATION REPORT
----------------------------------------

CLAIM
"Scientific studies show that vaccines cause autism in children"

AI PREDICTION
Misleading

MODEL CONFIDENCE
43.9% (Low confidence)

CLASS PROBABILITIES
False: 28.2%
Misleading: 43.9%
Reliable: 27.9%

WHY THE MODEL PREDICTED THIS
Important phrases:
* "studies show" (supports_prediction, rel. weight: 1.00)
* "vaccines cause" (supports_prediction, rel. weight: 0.71)
* "that vaccines" (supports_prediction, rel. weight: 0.65)

EVIDENCE VERIFICATION
Status:
CONTRADICTING

Evidence summary:
External evidence from authoritative sources conflicts with or refutes the claim. Found 3 source(s) indicating factual dispute, negation, or misattribution.

SOURCES
1. Vaccines and autism
   Source:    Wikipedia
   URL:       https://en.wikipedia.org/wiki/Vaccines_and_autism
   Relation:  CONTRADICTS
   Relevance: 0.57

2. Wakefield MMR-autism fraud
   Source:    Wikipedia
   URL:       https://en.wikipedia.org/wiki/Wakefield_MMR-autism_fraud
   Relation:  CONTRADICTS
   Relevance: 0.57

3. MMR vaccine and autism
   Source:    Wikipedia
   URL:       https://en.wikipedia.org/wiki/MMR_vaccine_and_autism
   Relation:  CONTRADICTS
   Relevance: 0.47

FINAL ASSESSMENT
Potentially False -- retrieved evidence contradicts the claim, but model confidence is low.

RESPONSIBLE AI NOTE
Model confidence is not factual certainty.
Evidence retrieval is separate from the classifier prediction.
When evidence is insufficient, the claim remains unverified.
----------------------------------------
```

---

## 10. Responsible AI Limitations & Safeguards
1. **Zero Fabrication**: No placeholder URLs (`example.com`), mock fact-checkers, or invented citations exist in the system.
2. **Unverifiable as Verification State**: "Unverifiable" exists strictly as an evidence retrieval outcome, not as a supervised classifier class.
3. **No Algorithmic Bias Override**: The system explicitly warns the user that machine learning models capture stylistic correlations rather than ground-truth real-world facts.
