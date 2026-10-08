import re
from typing import Dict, Any, List

# Common noise prefixes in political claims and news headlines
PREFIX_PATTERNS = [
    r"^(says\s+that\s+|says\s+)",
    r"^(on\s+support\s+for\s+|on\s+possibly\s+|on\s+)",
    r"^(claims\s+that\s+|claims\s+)",
    r"^(stated\s+that\s+|stated\s+)",
    r"^(argues\s+that\s+|argues\s+)",
    r"^(tweeted\s+that\s+|tweeted\s+)",
    r"^(breaking:\s*|exclusive:\s*|alert:\s*)",
    r"^(did\s+you\s+know\s+that\s+)",
]

# Stop words to remove during search query generation
SEARCH_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "through", "about", "for", "is", "of", "while", "during",
    "to", "from", "in", "out", "on", "off", "over", "under", "again", "further",
    "at", "by", "with", "into", "throughout", "between", "up", "down",
    "it", "its", "it's", "he", "she", "they", "them", "his", "her", "their",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "can", "could", "should", "would", "may", "might", "must", "will",
    "says", "said", "say"
}

def clean_claim_text(text: str) -> str:
    """Strip common reporting attribution frames and clean whitespace."""
    if not text:
        return ""
    
    cleaned = text.strip()
    
    # Remove leading quote marks or ellipses
    cleaned = re.sub(r'^[“"\'\.\s]+|[”"\'\.\s]+$', '', cleaned)
    
    # Strip common noise prefixes (e.g. "Says...", "On possibly...")
    for pattern in PREFIX_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
        
    return cleaned

def generate_search_query(text: str, max_terms: int = 8) -> str:
    """Generate a focused, neutral search query from a claim."""
    cleaned = clean_claim_text(text)
    
    # Tokenize and retain informative words (non-stopwords and alphanumeric)
    words = re.findall(r'\b[A-Za-z0-9\$\%]+(?:\-[A-Za-z0-9]+)?\b', cleaned)
    
    # Identify key terms
    key_terms = []
    for w in words:
        if w.lower() not in SEARCH_STOPWORDS:
            key_terms.append(w)
            
    # If too few terms remain, keep original words
    if len(key_terms) < 3 and len(words) >= 3:
        key_terms = words
        
    selected_terms = key_terms[:max_terms]
    return " ".join(selected_terms)

def extract_claim(text: str) -> Dict[str, Any]:
    """Identify the core factual claim and produce a clean search query.
    
    Returns:
        dict: {
            "original_text": str,
            "claim": str,
            "search_query": str,
            "is_short_claim": bool
        }
    """
    if not text or not text.strip():
        return {
            "original_text": "",
            "claim": "",
            "search_query": "",
            "is_short_claim": True
        }
        
    stripped = text.strip()
    cleaned_claim = clean_claim_text(stripped)
    search_query = generate_search_query(cleaned_claim)
    
    word_count = len(stripped.split())
    is_short = word_count <= 25
    
    return {
        "original_text": stripped,
        "claim": cleaned_claim if cleaned_claim else stripped,
        "search_query": search_query if search_query else stripped,
        "is_short_claim": is_short
    }

if __name__ == "__main__":
    test_inputs = [
        "Says George Washington said a free people should be armed to guard against government tyranny.",
        "On possibly raising the Social Security retirement age.",
        "Romneycare has killed 18,000 Massachusetts jobs."
    ]
    for inp in test_inputs:
        res = extract_claim(inp)
        print(f"Original: {res['original_text']}")
        print(f"Claim:    {res['claim']}")
        print(f"Query:    {res['search_query']}\n")
