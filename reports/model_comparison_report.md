# Phase 5: Model Evaluation, Error Analysis & Production Model Selection Report

## A. Dataset Conditions
The dataset utilized in Phase 5 comprises processed, leak-free news and fact-check claims across three target classes:
- **False** (outright fabricated, pants-on-fire, or completely false assertions)
- **Misleading** (half-true, mostly false, distorted context, or exaggerated claims)
- **Reliable** (verified true, mostly true, or evidence-corroborated reports)

Following the Phase 2 audit and deduplication pipeline, duplicate records and cross-split overlaps between train, validation, and test sets were completely eliminated (0 duplicate leakage). Note that **"Unverifiable"** is not a supervised training class in this dataset, as unverified claims require dynamic external retrieval rather than static lexical pattern matching.

---

## B, C, D. Sample Sizes & Dataset Discrepancy Resolution

### Actual Physical Dataset Splits on Disk:
The actual clean files produced and stored in `data/processed/` (derived from the deduplicated LIAR 3-class corpus) consist of **11,718 total records**:
- **Train split (`data/processed/train.csv`)**: **8,202 samples** (70.0%)
- **Validation split (`data/processed/validation.csv`)**: **1,758 samples** (15.0%)
- **Test split (`data/processed/test.csv`)**: **1,758 samples** (15.0%)
- **Master Clean (`data/processed/master_clean.csv`)**: **11,718 samples** (100.0%)

### Evaluation Setup for Each Model:
| Metric / Dataset Split | TF-IDF + Logistic Regression (Model A) | DistilBERT (Model B) | Physical Disk Splits | Theoretical Multi-Source Estimate |
|---|---|---|---|---|
| **Training Sample Size** | 8,202 samples (100% of train.csv) | 2,000 samples (CPU subsampled) | 8,202 samples | 31,540 samples |
| **Validation Sample Size** | 1,758 samples (100% of val.csv) | 500 samples (CPU subsampled) | 1,758 samples | 6,758 samples |
| **Test Sample Size** | 1,758 samples (100% of test.csv) | 500 samples (CPU subsampled) | 1,758 samples | 6,759 samples |
| **Total Split Size** | 11,718 samples | 3,000 samples | 11,718 samples | 45,057 samples |

### Explanation of the Discrepancy:
- **Phase 2 Planning / Theoretical Multi-Source Estimate (45,057 total: 31,540 train / 6,758 val / 6,759 test)**:
  This figure represented the projected size if raw ISOT articles (~44,898 records) were merged with LIAR claims. However, ISOT contains only binary labels (`Fake` / `True`), lacking the intermediate `Misleading` / fine-grained veracity taxonomy required for TruthLens AI's 3-way classification.
- **Actual Physical Dataset in `data/processed/` (11,718 total: 8,202 train / 1,758 val / 1,758 test)**:
  To maintain a clean 3-way distribution (`False`, `Misleading`, `Reliable`) without artificial label distortion or extreme class imbalance, the deduplicated LIAR benchmark was preserved as the active clean corpus. Both `train_baseline.py` and `train_transformer.py` read directly from `data/processed/` on disk, evaluating against this verified 11,718-record dataset.

*Sampling Method for DistilBERT*: Random pseudo-random sampling (`random_state=42`, `replace=False`) from `train.csv` (2,000), `validation.csv` (500), and `test.csv` (500) due to CPU compute constraints.

---

## E & F. Overall Performance Comparison

| Evaluation Metric | TF-IDF + Logistic Regression | DistilBERT (`distilbert-base-uncased`) | Delta (DistilBERT vs Baseline) | Winner |
|---|---|---|---|---|
| **Validation Accuracy** | 0.4630 | **0.4780** | +0.0150 (+1.50%) | **DistilBERT** |
| **Validation Macro F1** *(Primary)* | 0.3969 | **0.4102** | +0.0133 (+1.33%) | **DistilBERT** |
| **Validation Weighted F1** | 0.4366 | *N/A (tracked Macro)* | — | — |
| **Test Accuracy** | 0.4602 | **0.4660** | +0.0058 (+0.58%) | **DistilBERT** |
| **Test Macro F1** | **0.3993** | 0.3933 | -0.0060 (-0.60%) | **TF-IDF + LR** |
| **Test Weighted F1** | **0.4373** | 0.4341 | -0.0032 (-0.32%) | **TF-IDF + LR** |

---

## G. Per-Class Performance Comparison

### Test Set Per-Class Metrics

| Target Class | Metric | TF-IDF + Logistic Regression (N=1,758) | DistilBERT (N=500) | Analysis |
|---|---|---|---|---|
| **False** | Precision | 0.3884 | **0.4545** | DistilBERT has higher precision (+6.6%) |
| | Recall | **0.1257** | 0.0909 | Both models exhibit low recall on False claims |
| | **F1-Score** | **0.1899** | 0.1515 | TF-IDF + LR retains slightly higher F1 (+3.8%) |
| **Misleading** | Precision | **0.4602** | 0.4575 | Comparable precision (~46%) |
| | Recall | **0.5783** | 0.5594 | High recall across both architectures |
| | **F1-Score** | **0.5125** | 0.5033 | Comparable F1 (~51%) |
| **Reliable** | Precision | 0.4718 | **0.4762** | DistilBERT slightly higher precision |
| | Recall | 0.5215 | **0.5851** | DistilBERT achieves substantially higher recall (+6.4%) |
| | **F1-Score** | 0.4954 | **0.5251** | DistilBERT achieves superior F1 (+3.0%) |

### Validation Set Per-Class Metrics (Reference)
- **TF-IDF + LR**:
  - `False`: Precision: 0.4556, Recall: 0.1096, F1: 0.1767
  - `Misleading`: Precision: 0.4438, Recall: 0.5749, F1: 0.5009
  - `Reliable`: Precision: 0.4874, Recall: 0.5414, F1: 0.5130

---

## H. Confusion Matrices

### 1. TF-IDF + Logistic Regression (Test Split, N=1,758)
Classes: `[False, Misleading, Reliable]`
```
                Predicted False    Predicted Misleading    Predicted Reliable
Actual False               47                    187                   140
Actual Misleading          45                    410                   254
Actual Reliable            29                    294                   352
```

### 2. DistilBERT (Test Subset, N=500)
Classes: `[False, Misleading, Reliable]`
```
                Predicted False    Predicted Misleading    Predicted Reliable
Actual False               10                     64                    36
Actual Misleading           4                    113                    85
Actual Reliable             8                     70                   110
```

Visualizations generated and saved to:
- `reports/figures/baseline_confusion_matrix.png`
- `reports/figures/distilbert_confusion_matrix.png`
- `reports/figures/model_comparison_confusion_matrices.png`

---

## I. Error Analysis (Representative Predictions & Linguistic Factors)

The following representative misclassifications were extracted directly from the actual test evaluation logs:

### 1. Actual False → Predicted Reliable
- **TF-IDF Sample**: *"Its been 4 and a half years since the United States Senate passed a budget..."*
- **DistilBERT Sample**: *"If all of the [Bush-era] tax cuts expire on schedule, the budget will be close to being balanced in four years..."*
- **Linguistic Analysis / Inference**: Both models misclassify these false statements as Reliable because the phrasing uses formal legislative and economic terminology ("Senate passed a budget", "tax cuts expire", "budget will be balanced"). The sentence structure mimics credible, sober reporting. Without real-time external fact verification, the classifiers associate institutional vocabulary with reliability.

### 2. Actual False → Predicted Misleading
- **TF-IDF Sample**: *"Says George Washington said a free people should be armed to guard against government tyranny..."*
- **DistilBERT Sample**: *"Say easing restrictions on selling alcohol on Sundays will result in more traffic crashes and fatalities..."*
- **Linguistic Analysis / Inference**: These false assertions involve political debates, disputed quotes, or policy cause-and-effect claims. The vocabulary overlaps heavily with legitimate political discussions and partial truths, pulling the model's prediction toward the middle ground ("Misleading") rather than outright "False".

### 3. Actual Reliable → Predicted False
- **TF-IDF Sample**: *"When President Barack Obama said ISIS, or ISIL, was contained, he was responding very specifically to the geographic expansion of ISIL in Iraq and Syria..."*
- **DistilBERT Sample**: *"Issue 2 makes it illegal for us to negotiate for enough firefighters to do the job..."*
- **Linguistic Analysis / Inference**: Contains conflict-laden, polarized, or crisis terminology ("ISIS", "ISIL", "illegal", "firefighters dispute"). In typical training text, sensational or combative terminology is strongly associated with false propaganda, leading the models to false-positive classification on truthful defensive clarifications.

### 4. Actual Reliable → Predicted Misleading
- **TF-IDF Sample**: *"Says he vetoed $250,000 from the budget for a program to learn how to catch rainwater..."*
- **DistilBERT Sample**: *"Says DonaldTrump proposes tax cuts, too -- $3 trillion for millionaires like himself and $2 trillion for corporations like his..."*
- **Linguistic Analysis / Inference**: Short political soundbites often employ adversarial framing, exaggerated emphasis, and partisan barbs. Because the text lacks corroborating citations or full contextual nuance in short-claim form, the model infers hyperbole and assigns the "Misleading" label.

### 5. Actual Misleading → Predicted False
- **TF-IDF Sample**: *"Under President George W. Bush, the U.S. spent $1.3 trillion on tax cuts for the wealthy and trillions each on a war and on Medicare..."*
- **DistilBERT Sample**: *"Says opponent Chad Chadwell wants condom techniques demonstrated to your children..."*
- **Linguistic Analysis / Inference**: Statements featuring explosive or lurid accusations ("trillions on tax cuts for the wealthy", "condom techniques demonstrated to children") trigger the model's highest falsehood activations due to inflammatory wording, even when human fact-checkers rated them as partially distorted or half-true.

### 6. Actual Misleading → Predicted Reliable
- **TF-IDF Sample**: *"Romneycare has killed 18,000 Massachusetts jobs..."*
- **DistilBERT Sample**: *"Texas has the lowest crime rate in this state since 1968 because of changes in law regarding nonviolent drug offenders..."*
- **Linguistic Analysis / Inference**: Features precise numeric claims, dates, and geographic specificity ("18,000 jobs", "since 1968", "Texas"). The measured, empirical tone confers a false sense of objective authority that misleads lexical and contextual feature extractors into predicting Reliable.

---

## J. Fairness & Methodological Limitations
1. **Asymmetric Training Scale**:
   - The TF-IDF baseline was trained on 8,202 samples.
   - DistilBERT was trained on only 2,000 samples due to local CPU training constraints.
2. **Subsampled Test Scale**:
   - TF-IDF was evaluated on 1,758 test instances.
   - DistilBERT was evaluated on 500 test instances.
3. **Hardware Constraints**:
   - Transformer fine-tuning was limited to 2 epochs, batch size of 8, and maximum sequence length of 128 tokens on CPU without GPU acceleration.
4. **Conclusion on Comparison**:
   - Neither model can be claimed as definitively or universally superior based solely on this experiment. The comparison demonstrates comparative prototype behavior under hardware-constrained conditions.

---

## K. Model Selection Decision

### Decision Logic:
- **Primary Metric**: Validation Macro F1.
  - DistilBERT: **0.4102**
  - TF-IDF + Logistic Regression: **0.3969**
  - *DistilBERT is the validation winner on the pre-established primary criterion.*
- **Secondary Metrics**:
  - Validation Accuracy: DistilBERT (**0.4780**) > TF-IDF (0.4630)
  - Test Accuracy: DistilBERT (**0.4660**) > TF-IDF (0.4602)
  - Test Macro F1: TF-IDF (**0.3993**) > DistilBERT (0.3933)
  - Reliable Class F1: DistilBERT (**0.5251**) > TF-IDF (0.4954)
- **Deployment & Architecture Consideration**:
  - DistilBERT produces contextual token-level hidden states and self-attention distributions that directly enable model explainability (token saliency / attention maps) in subsequent phases, unlike linear bag-of-words models.

### Selected Production Model:
**DistilBERT (`distilbert-base-uncased`)**

### Official Selection Statement:
> "DistilBERT is selected as the production NLP model for the prototype because it achieved the highest validation Macro F1 in the controlled experiment. However, its performance should be considered provisional because the transformer was trained on a CPU-constrained subset."

---

## Responsible AI & Fact-Checking Disclosure
> **CRITICAL RESPONSIBLE AI STATEMENT**:
> 
> The classifier predicts stylistic, lexical, and discourse patterns learned from labeled training corpora. A high confidence score does not prove that an empirical claim is factually true or verified.
> 
> **"Unverifiable"** is not a supervised class in the current training data.
> 
> Later phases will integrate evidence retrieval and claim-verification pipelines to determine whether external authoritative sources support, contradict, or provide insufficient evidence to verify a claim.
