import os
import re
import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# Project root and model path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "production"
if not DEFAULT_MODEL_DIR.exists():
    DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "transformer"

# Configurable confidence threshold
EXPLANATION_CONFIDENCE_THRESHOLD = 0.60

# Common english stopwords to exclude from single-token phrase highlights
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "through", "about", "for", "is", "of", "while", "during",
    "to", "from", "in", "out", "on", "off", "over", "under", "again", "further",
    "at", "by", "with", "into", "throughout", "between", "up", "down", "in", "out",
    "it", "its", "it's", "he", "she", "they", "them", "his", "her", "their",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "can", "could", "should", "would", "may", "might", "must", "will"
}

class DistilBertExplainer:
    """Explainable AI engine for TruthLens AI using Integrated Gradients

    attribution on DistilBERT token embeddings.
    """
    def __init__(self, model_path: Optional[str] = None, confidence_threshold: float = EXPLANATION_CONFIDENCE_THRESHOLD):
        self.model_path = str(model_path or DEFAULT_MODEL_DIR)
        self.confidence_threshold = confidence_threshold
        self.tokenizer = None
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.classes = ["False", "Misleading", "Reliable"]
        
    def load(self):
        """Load tokenizer and model if not already loaded."""
        if self.model is None or self.tokenizer is None:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
            self.model.to(self.device)
            self.model.eval()

    def _compute_integrated_gradients(self, text: str, steps: int = 5):
        """Compute Integrated Gradients on input token embeddings relative to the zero baseline.
        Returns:
            input_ids, offset_mapping, attributions (per-token), probs, pred_idx
        """
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=128,
            return_offsets_mapping=True
        )
        
        offset_mapping = inputs.pop("offset_mapping")[0].tolist()
        input_ids = inputs["input_ids"].to(self.device)
        attention_mask = inputs["attention_mask"].to(self.device)

        embedding_layer = self.model.get_input_embeddings()
        embeddings = embedding_layer(input_ids)
        
        # Forward pass to determine probabilities and top class
        with torch.no_grad():
            init_outputs = self.model(inputs_embeds=embeddings, attention_mask=attention_mask)
            logits = init_outputs.logits
            probs = torch.nn.functional.softmax(logits, dim=-1)[0]
            pred_idx = logits.argmax(dim=-1).item()

        # Integrated Gradients baseline: zero embedding
        baseline = torch.zeros_like(embeddings)
        grads_accum = torch.zeros_like(embeddings)

        for step in range(1, steps + 1):
            alpha = step / steps
            interpolated = baseline + alpha * (embeddings - baseline)
            interpolated = interpolated.clone().detach().requires_grad_(True)
            
            outputs = self.model(inputs_embeds=interpolated, attention_mask=attention_mask)
            target_logit = outputs.logits[0, pred_idx]
            target_logit.backward()
            
            grads_accum += interpolated.grad

        avg_grads = grads_accum / steps
        # Attribution = (embedding - baseline) * average_gradients summed across embedding dimension
        ig_attributions = ((embeddings - baseline) * avg_grads).sum(dim=-1).squeeze(0)
        attributions = ig_attributions.detach().cpu().numpy()

        return input_ids[0].tolist(), offset_mapping, attributions, probs, pred_idx

    def _extract_important_phrases(self, text: str, offset_mapping: List[List[int]], attributions: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
        """Merge subword tokens using character offset mapping and extract top influential phrases."""
        raw_words = []
        current_start = None
        current_end = None
        current_attr = 0.0

        for (start, end), attr in zip(offset_mapping, attributions):
            if start == end:  # Skip special tokens ([CLS], [SEP])
                continue
            if current_start is None:
                current_start, current_end, current_attr = start, end, attr
            elif start == current_end:  # Contiguous subword or contiguous punctuation
                current_end = end
                current_attr += attr
            else:
                word_text = text[current_start:current_end].strip()
                if word_text:
                    raw_words.append({
                        "phrase": word_text,
                        "raw_score": current_attr,
                        "start": current_start,
                        "end": current_end
                    })
                current_start, current_end, current_attr = start, end, attr

        if current_start is not None:
            word_text = text[current_start:current_end].strip()
            if word_text:
                raw_words.append({
                    "phrase": word_text,
                    "raw_score": current_attr,
                    "start": current_start,
                    "end": current_end
                })

        if not raw_words:
            return []

        # Find maximum absolute attribution for normalization
        max_abs = max(abs(w["raw_score"]) for w in raw_words) or 1.0

        # Filter and candidate generation
        candidates = []
        for w in raw_words:
            clean_phrase = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', w["phrase"]).strip()
            if not clean_phrase or clean_phrase.lower() in STOPWORDS or len(clean_phrase) < 2:
                continue
            normalized_importance = float(min(1.0, max(0.05, round(float(abs(w["raw_score"]) / max_abs), 2))))
            direction = "supports_prediction" if w["raw_score"] >= 0 else "opposes_prediction"
            candidates.append({
                "phrase": clean_phrase,
                "importance": normalized_importance,
                "direction": direction,
                "raw_score": float(w["raw_score"])
            })

        # Also identify adjacent 2-word combinations if both contribute positively
        for i in range(len(raw_words) - 1):
            w1 = raw_words[i]
            w2 = raw_words[i + 1]
            if w1["raw_score"] > 0 and w2["raw_score"] > 0:
                p1 = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', w1["phrase"]).strip()
                p2 = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', w2["phrase"]).strip()
                if p1 and p2 and (p1.lower() not in STOPWORDS or p2.lower() not in STOPWORDS):
                    bigram = f"{p1} {p2}"
                    combined_raw = float((w1["raw_score"] + w2["raw_score"]) / 1.5)
                    normalized_imp = float(min(1.0, max(0.05, round(float(abs(combined_raw) / max_abs), 2))))
                    candidates.append({
                        "phrase": bigram,
                        "importance": normalized_imp,
                        "direction": "supports_prediction",
                        "raw_score": combined_raw
                    })

        # Deduplicate candidates while retaining highest importance
        unique_phrases = {}
        for c in candidates:
            p_lower = c["phrase"].lower()
            if p_lower not in unique_phrases or c["importance"] > unique_phrases[p_lower]["importance"]:
                unique_phrases[p_lower] = {
                    "phrase": c["phrase"],
                    "importance": float(c["importance"]),
                    "direction": c["direction"]
                }

        sorted_phrases = sorted(unique_phrases.values(), key=lambda x: x["importance"], reverse=True)
        return sorted_phrases[:top_k]

    def explain(self, text: str) -> Dict[str, Any]:
        """Explain the model's prediction for the input text using Integrated Gradients."""
        self.load()
        
        if not text or not text.strip():
            return {
                "prediction": {"label": "Reliable", "confidence": 0.3333},
                "probabilities": {"False": 0.3333, "Misleading": 0.3333, "Reliable": 0.3334},
                "explanation": {
                    "summary": "Input text was empty. Default neutral baseline returned.",
                    "confidence_status": "Low confidence",
                    "important_phrases": []
                },
                "responsible_ai": {
                    "confidence_note": "Model confidence is not factual certainty.",
                    "verification_note": "Evidence retrieval is required for evidence-based verification."
                }
            }

        input_ids, offsets, attributions, probs, pred_idx = self._compute_integrated_gradients(text, steps=5)
        
        # Build class probabilities dictionary
        class_probs = {}
        for idx in range(len(probs)):
            label = self.model.config.id2label[idx]
            class_probs[label] = round(float(probs[idx].item()), 4)

        predicted_label = self.model.config.id2label[pred_idx]
        confidence = round(float(probs[pred_idx].item()), 4)

        # Confidence status
        if confidence >= self.confidence_threshold:
            confidence_status = "Model prediction"
            summary = (
                f"The model classified this text as {predicted_label} with {confidence * 100:.1f}% model confidence. "
                "Several phrases in the input contributed strongly to this prediction. These phrases reflect "
                "patterns learned from the training data; they do not independently establish whether the claim is factually true or false."
            )
        else:
            confidence_status = "Low confidence"
            summary = (
                f"The model assigned a provisional label of {predicted_label} with {confidence * 100:.1f}% model confidence "
                f"(classified as Low confidence because confidence is below the {int(self.confidence_threshold * 100)}% threshold). "
                "The probabilities are distributed among multiple classes. These phrases reflect training associations and "
                "must not be interpreted as definitive fact-checking."
            )

        important_phrases = self._extract_important_phrases(text, offsets, attributions, top_k=5)

        return {
            "prediction": {
                "label": predicted_label,
                "confidence": confidence
            },
            "probabilities": class_probs,
            "explanation": {
                "summary": summary,
                "confidence_status": confidence_status,
                "important_phrases": important_phrases
            },
            "responsible_ai": {
                "confidence_note": "Model confidence is not factual certainty.",
                "verification_note": "Evidence retrieval is required for evidence-based verification."
            }
        }

# Global singleton instance for efficient reuse across API calls
_global_explainer: Optional[DistilBertExplainer] = None

def get_explainer() -> DistilBertExplainer:
    global _global_explainer
    if _global_explainer is None:
        _global_explainer = DistilBertExplainer()
        _global_explainer.load()
    return _global_explainer

def explain_prediction(text: str, confidence_threshold: float = EXPLANATION_CONFIDENCE_THRESHOLD) -> Dict[str, Any]:
    """Public interface function for Flask API integration."""
    explainer = get_explainer()
    if confidence_threshold != explainer.confidence_threshold:
        explainer.confidence_threshold = confidence_threshold
    return explainer.explain(text)

if __name__ == "__main__":
    import json
    sample_text = "Romneycare has killed 18,000 Massachusetts jobs."
    print("Testing explain_prediction on sample text:")
    result = explain_prediction(sample_text)
    print(json.dumps(result, indent=2))
