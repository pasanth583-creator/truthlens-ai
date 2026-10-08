# TruthLens AI — Phase 5 Model Error Analysis Report

This document presents a comprehensive, empirical error analysis using actual predictions from both **Model A (TF-IDF + Logistic Regression)** evaluated on the full test split ($N=1,758$) and **Model B (DistilBERT)** evaluated on the test subset ($N=500$).

All examples are taken directly from model prediction logs on the test dataset.

---

## Error Category Breakdown & Actual Model Predictions

### 1. Actual False → Predicted Misleading
- **Frequency**:
  - Baseline (TF-IDF + LR): **187** instances
  - DistilBERT: **64** instances
- **Representative Examples**:
  - *Baseline*: `"Says George Washington said a free people should be armed to guard against government tyranny..."`
  - *Baseline*: `"On possibly raising the Social Security retirement age..."`
  - *DistilBERT*: `"Say easing restrictions on selling alcohol on Sundays will result in more traffic crashes and fatalities..."`
  - *DistilBERT*: `"Social science is irrefutable that children are better off being raised by a mom and a dad..."`
- **Linguistic & Semantic Inference**:
  These statements involve political discourse, historical attribution, and contested social/economic assertions. Because they use policy and debate vocabulary typical of "half-true" or "barely-true" claims, the models classify them as moderate distortion (*Misleading*) rather than outright fabrication (*False*).

---

### 2. Actual False → Predicted Reliable
- **Frequency**:
  - Baseline (TF-IDF + LR): **140** instances
  - DistilBERT: **36** instances
- **Representative Examples**:
  - *Baseline*: `"Its been 4 and a half years since the United States Senate passed a budget..."`
  - *Baseline*: `"The wealth gap between blacks and whites in the United States is greater than the black-white wealth gap was in apartheid South Africa..."`
  - *DistilBERT*: `"If all of the [Bush-era] tax cuts expire on schedule, the budget will be close to being balanced in four years..."`
  - *DistilBERT*: `"Says the number-one source of illegal immigration is people legally coming to the United States on a tourist visa or a student visa and then..."`
- **Linguistic & Semantic Inference**:
  These claims utilize authoritative, sober, and formal legislative terminology ("United States Senate", "passed a budget", "wealth gap", "balanced in four years"). The syntax mimics institutional reporting, tricking both lexical and contextual models into predicting *Reliable* without real-time external knowledge retrieval.

---

### 3. Actual Misleading → Predicted False
- **Frequency**:
  - Baseline (TF-IDF + LR): **45** instances
  - DistilBERT: **4** instances
- **Representative Examples**:
  - *Baseline*: `"Under President George W. Bush, the U.S. spent $1.3 trillion on tax cuts for the wealthy and trillions each on a war and on Medicare..."`
  - *Baseline*: `"On support for a military strike on Syria..."`
  - *DistilBERT*: `"Stopped by Smiley Cookie to pick up some great cookies for the family, along with Rudy..."`
  - *DistilBERT*: `"Says opponent Chad Chadwell wants condom techniques demonstrated to your children..."`
- **Linguistic & Semantic Inference**:
  These statements contain hyperbolic phrases, sensational political attacks, or extreme numbers ("trillions on war", "condom techniques demonstrated"). The strong sensationalist rhetoric triggers the model's highest falsehood activations, pushing them from *Misleading* (partial truth) into *False*.

---

### 4. Actual Misleading → Predicted Reliable
- **Frequency**:
  - Baseline (TF-IDF + LR): **254** instances
  - DistilBERT: **85** instances
- **Representative Examples**:
  - *Baseline*: `"Romneycare has killed 18,000 Massachusetts jobs..."`
  - *Baseline*: `"The Atlanta areas water planning district is now the national leader in conservation..."`
  - *DistilBERT*: `"Texas has the lowest crime rate in this state since 1968 because of changes in law regarding nonviolent drug offenders..."`
  - *DistilBERT*: `"Says Mitch McConnell voted three times for corporate tax breaks that send Kentucky jobs overseas..."`
- **Linguistic & Semantic Inference**:
  These claims present specific metrics, dates, and legislative actions ("18,000 jobs", "since 1968", "voted three times"). The measured, empirical tone confers a false sense of objective credibility, concealing cherry-picked or distorted facts from purely surface-level NLP models.

---

### 5. Actual Reliable → Predicted False
- **Frequency**:
  - Baseline (TF-IDF + LR): **29** instances
  - DistilBERT: **8** instances
- **Representative Examples**:
  - *Baseline*: `"When President Barack Obama said ISIS, or ISIL, was contained, he was responding very specifically to the geographic expansion of ISIL in Iraq and Syria..."`
  - *Baseline*: `"Says he had to impose tougher cost controls on state employees than any previous Wisconsin governor..."`
  - *DistilBERT*: `"Says Paul Ryans budget would turn Medicare into a voucher..."`
  - *DistilBERT*: `"Issue 2 makes it illegal for us to negotiate for enough firefighters to do the job..."`
- **Linguistic & Semantic Inference**:
  Statements mentioning controversial actors, terror groups ("ISIS/ISIL"), or polarizing conflicts ("illegal", "voucher") share significant lexical overlap with partisan disinformation corpora. The model associates these contentious tokens with low veracity, falsely penalizing factual reports.

---

### 6. Actual Reliable → Predicted Misleading
- **Frequency**:
  - Baseline (TF-IDF + LR): **294** instances
  - DistilBERT: **70** instances
- **Representative Examples**:
  - *Baseline*: `"You ... said that Barack Obama was not ready to be commander in chief..."`
  - *Baseline*: `"Says he vetoed $250,000 from the budget for a program to learn how to catch rainwater..."`
  - *DistilBERT*: `"Says DonaldTrump proposes tax cuts, too -- $3 trillion for millionaires like himself and $2 trillion for corporations like his..."`
  - *DistilBERT*: `"On support for gay marriage..."`
- **Linguistic & Semantic Inference**:
  Short soundbites and contentious political quotes often lack context, citations, and neutral framing. Due to their brevity and rhetorical edge, the model defaults to the ambiguous middle class (*Misleading*).

---

## Summary of Findings & Implications for TruthLens AI

1. **Surface Tone vs. Factuality**:
   Models rely heavily on stylistic indicators (formality vs. sensationalism) rather than truth value. A falsehood delivered in sober, official prose is frequently classified as *Reliable*, while a factual claim discussing contentious topics is frequently flagged as *Misleading* or *False*.
2. **Need for External Evidence Retrieval**:
   This error analysis empirically proves that an NLP classifier alone is insufficient for reliable fact-checking. A high model confidence score simply indicates stylistic conformity to training patterns.
3. **Role of Subsequent Phases**:
   Phase 6 and downstream verification modules must incorporate dynamic knowledge retrieval and evidence verification to corroborate claims against authoritative sources rather than relying solely on classifier predictions.
