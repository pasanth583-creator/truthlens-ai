# TruthLens AI — Hackathon & Live Demo Guide

This guide provides a structured 3–5 minute walkthrough script and demonstration playbook for presenting **TruthLens AI** to judges, reviewers, and hackathon audiences.

---

## 1. Quick Demo Cheatsheet (3–5 Minute Flow)

| Time | Phase | Action / Screen | Key Talking Point |
|---|---|---|---|
| **0:00 – 0:30** | **The Problem** | Home Page (`/`) | Misinformation spreads faster than fact-checking. Pure black-box models hallucinate certainty, while standard search lacks NLP context. We need an explainable, dual-signal system. |
| **0:30 – 1:15** | **Live Analysis** | Analyze Page (`/analyze`) | Submit Claim 1: *"Drinking lemon water cures all forms of cancer."* |
| **1:15 – 2:00** | **Explainability & Evidence** | Result Page (`/result/<id>`) | Highlight DistilBERT's `False` prediction, class probability breakdown, Integrated Gradients token attribution (`cures`, `all forms`), and contradicting external evidence. |
| **2:00 – 3:00** | **The "Aha!" Moment (Conflict Detection)** | Analyze Page (`/analyze`) | Submit Claim 2: *"George Washington was the first President of the United States."* Show **Conflicting Signals Alert** — explain why dual-signal verification protects users from blind model trust. |
| **3:00 – 3:45** | **Audit Trail & System Memory** | History Page (`/history`) | Show the persistent analysis log in SQLite. Every query is auditable with full evidence snippets and timestamps. |
| **3:45 – 4:30** | **Responsible AI & Q&A** | About Page (`/about`) | Disclose dataset bounds, confidence thresholds, and system philosophy: decision-support assistance, not an autonomous oracle. |

---

## 2. Recommended Live Test Claims

Use these verified claims during your demonstration:

### Claim A: Debunked / Contradicted Assertion (Likely False)
- **Input Text**:
  ```text
  Drinking hot lemon water cures all forms of cancer immediately.
  ```
- **Expected Pipeline Behavior**:
  - **NLP Classifier**: Predicts `False` or `Misleading` with high confidence.
  - **Explainability**: Integrated Gradients highlights sensational absolute tokens (*"cures"*, *"all forms"*, *"immediately"*).
  - **Evidence Retrieval**: Retrieves medical consensus articles noting unproven claims.
  - **Verdict**: `LIKELY_FALSE` badge with contradicting evidence citation.

---

### Claim B: Verified Factual Assertion with Dual-Signal Safety (Conflicting Signals)
- **Input Text**:
  ```text
  George Washington was the first President of the United States.
  ```
- **Expected Pipeline Behavior**:
  - **NLP Classifier**: Predicts `Misleading` with low confidence (~0.47) due to stylistic similarities with historical quiz patterns in the dataset.
  - **Evidence Retrieval**: Authoritative Wikipedia records return high relevance supporting snippets confirming Washington as the first president.
  - **Verdict**: **`CONFLICTING_SIGNALS`**
- **Judge Narrative / Pitch**:
  > *"Notice what happened here: A pure black-box classifier would have misinformed the user. TruthLens AI detected that external factual evidence strongly supports the assertion despite the classifier's low-confidence linguistic prediction. The system flagged a Conflicting Signals warning and prioritized external evidence over stylistic artifacts."*

---

### Claim C: Obscure or Insufficient Evidence Claim (Unverified)
- **Input Text**:
  ```text
  The municipal board of town 78941 enacted policy regulation 482910 on Tuesday.
  ```
- **Expected Pipeline Behavior**:
  - **NLP Classifier**: Predicts a class with low confidence.
  - **Evidence Retrieval**: External search returns 0 matching authoritative sources (`insufficient`).
  - **Verdict**: **`UNVERIFIED / INSUFFICIENT EVIDENCE`**
- **Judge Narrative / Pitch**:
  > *"Instead of hallucinating a true/false judgment when data is missing, TruthLens AI responsibly defaults to Unverified, preventing false certainty."*

---

## 3. Step-by-Step Presentation Script

### Step 1: Open the Application
1. Start Flask: `python app.py`
2. Navigate to `http://127.0.0.1:5000`
3. Point out the hero metrics: **11,718 curated records**, **DistilBERT NLP backbone**, **Integrated Gradients attribution**, and **Dual-Signal Verification**.

### Step 2: Navigate to Analysis
1. Click **"Analyze a Claim"** or use the top navigation.
2. Click one of the quick-load sample pills or paste Claim A.
3. Click **"Verify with TruthLens AI"** — notice the live spinner transition.

### Step 3: Walk Through the Result Screen
1. **Verification Verdict**: Show the top alert banner and summary.
2. **Classifier Signal**: Point out the class probabilities chart (`False`, `Misleading`, `Reliable`) and confidence score.
3. **Explainability Tokens**: Highlight the word attribution badges showing which specific tokens drove the neural network's focus.
4. **External Evidence**: Scroll to the evidence cards displaying source title, domain, relevance score, stance (`contradicts`/`supports`), and snippet.

### Step 4: Demonstrate the History Page
1. Click **"History"** in the navigation.
2. Show that every query is preserved in SQLite with timestamps, status tags, and one-click access back to the full analysis view.

### Step 5: Highlight Responsible AI & Limitations
1. Navigate to **"About"** (`/about`).
2. Point out:
   - System is built for decision support, not autonomous censorship.
   - Low confidence (< 60%) is transparently labeled.
   - Integrated Gradients explains model behavior, not factual reality.
   - Dataset splits and CPU experimental boundaries are fully disclosed.

---

## 4. Key Questions & Ready Answers for Judges

**Q1: Why not just use a larger LLM via prompt engineering?**
> *A: Large LLMs are prone to hallucination, expensive to query, and opaque. TruthLens AI combines lightweight, locally fine-tuned transformers (DistilBERT) with formal mathematical explainability (Integrated Gradients) and real-time grounding in external authoritative sources.*

**Q2: How does your system handle genuine unverifiable claims?**
> *A: Many academic datasets lack ground-truth "unverifiable" labels. We explicitly model Unverified as an evidence retrieval outcome rather than forcing a 3-way classifier to guess. If evidence is insufficient, TruthLens AI refuses to output false certainty.*

**Q3: What happens when the model and evidence disagree?**
> *A: That is the core innovation of our Dual-Signal Decision Matrix. When the model and external evidence diverge, the system triggers a `CONFLICTING_SIGNALS` alert and advises human review, preventing black-box model bias from overriding facts.*
