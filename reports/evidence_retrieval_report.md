# TruthLens AI — Phase 7 Evidence Retrieval & Verification Report

## 1. Architecture Overview
TruthLens AI maintains a strict architectural separation between **Classifier-Based Style Prediction** (Phases 3–6) and **Evidence-Based Factual Verification** (Phase 7).

```
   [User Input Text / Article]
                │
                ├───► [DistilBERT Classifier + Integrated Gradients] ──► Predicted Style (False / Misleading / Reliable)
                │
                └───► [Claim Extractor]
                            │ (clean claim & search query)
                            ▼
                      [Modular Evidence Providers]
                            │ (Wikipedia API / Google Fact Check)
                            ▼
                      [Evidence Ranker & Stance Classifier]
                            │ (relevance scoring, authority bonus, relation detection)
                            ▼
                      [Verification Summary] (SUPPORTING / CONTRADICTING / INSUFFICIENT)
```

The model prediction and external evidence verification are kept strictly independent: a model prediction of "False" does not bias the evidence status, and "Insufficient Evidence" never alters the model's classification.

---

## 2. Claim Extraction
Implemented in `services/claim_extractor.py`:
- **Noise Stripping**: Removes reporting attribution prefixes (e.g. `"Says that..."`, `"On possibly..."`, `"Claims that..."`, `"Did you know that..."`) and quote markers.
- **Search Query Generation**: Filters common stopwords while preserving key entities, numbers, and predicates to generate a concise, neutral query (maximum 8 terms).
- **Claim Preservation**: Short claims retain original wording to avoid losing semantic nuances.

---

## 3. Modular Search Providers
Implemented in `services/evidence.py` under the `EvidenceProvider` abstract base class:
1. **WikipediaEvidenceProvider** (*Active / Available*):
   - Accesses Wikipedia's public Search API (`https://en.wikipedia.org/w/api.php`).
   - Requires no private API keys; returns verified article titles, snippets, and canonical URLs (`https://en.wikipedia.org/wiki/...`).
2. **GoogleFactCheckProvider** (*Modular / Configurable*):
   - Implements Google Fact Check Tools ClaimReview API integration.
   - Requires `GOOGLE_FACT_CHECK_API_KEY`. In the absence of an environment key, it safely reports unavailable without crashing or inventing credentials.

---

## 4. Evidence Ranking
Each retrieved source is scored via `calculate_relevance()` on a scale of $0.00$ to $1.00$:
- **Content Overlap**: Jaccard similarity and token overlap between the claim's content words and the source title + snippet.
- **Credibility Weight**: A $+0.15$ authority bonus is awarded to reputable domains (e.g., `.org` encyclopedias, `.gov`, `.edu`, and certified fact-checking domains).
- **Threshold**: Only sources scoring $\ge 0.35$ are retained for final verification.

---

## 5, 6, 7. Stance Classification Logic

### Supporting Evidence Logic
- **Definition**: Authoritative sources affirmatively corroborate the core factual assertion.
- **Markers**: Explicit confirmation tokens (`confirmed`, `verified`, `official records`, `enacted`, `passed`, `was the first`, `established that`) or direct identity assertion without negation.
- **Status Trigger**: Supporting sources outnumber conflicting sources among high-relevance results.

### Contradicting Evidence Logic
- **Definition**: Authoritative sources directly refute, debunk, or negate the claim.
- **Markers**: Explicit refutation tokens (`debunked`, `misattributed`, `hoax`, `untrue`, `disproven`, `refuted`, `myth`, `no evidence`, `fraud`, `does not cause`, `no relationship`, `no connection`).
- **Status Trigger**: Contradicting sources $\ge 1$ and equal to or greater than supporting sources.

### Insufficient Evidence Logic
- **Definition**: Available sources are sparse, exhibit low relevance ($< 0.35$), or discuss tangential background without proving or disproving the assertion.
- **Status Trigger**: Default state whenever neither strong support nor direct contradiction can be conclusively established. TruthLens AI never forces a verdict.

---

## 8. Source Reliability Approach
- TruthLens AI prioritizes verified institutional sources.
- No URLs or sources are fabricated. Every source title, URL, and snippet maps to real external records returned by the active provider.

---

## 9. Safe Fallback Behavior
When external searches return no relevant matches, the system outputs:
```json
{
    "evidence_status": "insufficient",
    "sources": [],
    "summary": "Insufficient reliable evidence was retrieved to verify this claim."
}
```
Placeholder domains (`example.com`, `test.com`), dummy titles, and fabricated URLs are strictly prohibited.

---

## 10 & 11. API Limitations & Rate Limiting
- **Rate Limiting**: Enforced via `MIN_REQUEST_INTERVAL = 0.2s` between outbound requests and a thread-safe in-memory cache with TTL of 3,600 seconds (1 hour).
- **Google Fact Check Limitation**: Without an API key, live ClaimReview queries are unavailable; the provider gracefully delegates to the Wikipedia API.

---

## 12. Responsible AI Considerations
- **Prediction vs. Verification**: Model predictions reflect learned linguistic patterns; evidence verification reflects external corroboration.
- **"Unverifiable" Handling**: "Unverifiable" is handled strictly at the evidence retrieval layer as `evidence_status = "insufficient"`, never as a fabricated class in the supervised NLP model.

---

## 13. Test Results Summary

Executed via `training/test_evidence.py`:

| Test Category | Claim | Query | Evidence Status | Retrieved Sources |
|---|---|---|---|---|
| **1. Supporting Evidence** | *"George Washington was the first President of the United States."* | `George Washington first President United States` | **SUPPORTING** | 4 sources (Wikipedia: *George Washington*, *First inauguration...*, etc.; Rel: 1.00, Relation: `supports`) |
| **2. Contradicting Evidence** | *"Scientific studies show that vaccines cause autism in children."* | `Scientific studies show vaccines cause autism children` | **CONTRADICTING** | 4 sources (Wikipedia: *MMR vaccine and autism*, *Wakefield MMR-autism fraud*, etc.; Relation: `contradicts`) |
| **3. Insufficient Evidence** | *"Obscure local town council committee passed municipal resolution 987654321xyz on Tuesday."* | `Obscure local town council committee passed municipal resolution` | **INSUFFICIENT** | 2 sources (Low relevance background mentions; Status: `insufficient`) |

**Zero fabricated URLs or placeholder sources were used.**
