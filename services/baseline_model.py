import joblib
from pathlib import Path
from typing import List, Tuple

# Paths to persisted model artifacts
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models" / "baseline"
VECTORIZER_PATH = MODELS_DIR / "tfidf_vectorizer.joblib"
MODEL_PATH = MODELS_DIR / "logistic_regression.joblib"

# Global caches for loaded objects
_vectorizer: Path | None = None
_model: Path | None = None

def load() -> Tuple:
    """Load the TF‑IDF vectorizer and Logistic Regression model, caching them.

    Returns:
        (vectorizer, model): tuple of the fitted TfidfVectorizer and trained
        LogisticRegression instance.
    """
    global _vectorizer, _model
    if _vectorizer is None or _model is None:
        _vectorizer = joblib.load(VECTORIZER_PATH)
        _model = joblib.load(MODEL_PATH)
    return _vectorizer, _model

def predict(texts: List[str]) -> List[str]:
    """Predict class labels for a list of raw text strings.

    Args:
        texts: List of article or post texts.

    Returns:
        List of predicted class names ("Reliable", "Misleading", "False", "Unverifiable").
    """
    vec, mdl = load()
    X = vec.transform(texts)
    return mdl.predict(X).tolist()

def predict_proba(texts: List[str]) -> List[List[float]]:
    """Return probability distributions for each input text.

    The order of probabilities follows ``model.classes_``.
    """
    vec, mdl = load()
    X = vec.transform(texts)
    return mdl.predict_proba(X).tolist()
