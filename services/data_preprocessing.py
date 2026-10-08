import re
import unicodedata

def clean_text(text: str) -> str:
    """Basic text cleaning:
    - Normalize Unicode characters
    - Remove non‑ASCII symbols
    - Collapse multiple spaces
    - Strip leading/trailing whitespace
    """
    # Normalize Unicode (NFKC)
    text = unicodedata.normalize('NFKC', text)
    # Remove control characters and non‑printable
    text = re.sub(r"[\r\n\t]+", " ", text)
    # Keep basic punctuation and alphanumerics
    text = re.sub(r"[^\w\s.,!?'-]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

def map_label(original_label: str) -> str:
    """Map dataset‑specific labels to the four project categories.
    Returns one of: 'Reliable', 'Misleading', 'False', 'Unverifiable'.
    If the label cannot be mapped, returns 'Unverifiable'.
    """
    label = original_label.strip().lower()
    # Expanded label sets for better coverage across source datasets
    reliable = {"true", "mostly-true", "barely-true", "real", "reliable", "accurate", "genuine", "verified"}
    misleading = {"half-true", "mostly-false", "misleading", "partially-true", "mixed", "unverified", "questionable"}
    false = {"false", "pants-on-fire", "fake", "fabricated", "incorrect", "untrue", "lie", "false (misinformation)"}
    if label in reliable:
        return "Reliable"
    if label in misleading:
        return "Misleading"
    if label in false:
        return "False"
    return "Unverifiable"
