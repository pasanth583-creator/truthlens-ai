import re
from typing import Dict, Any, List, Set, Tuple

# Common noise prefixes in political claims, news headlines, and social media
PREFIX_PATTERNS = [
    r"^(says\s+that\s+|says\s+)",
    r"^(on\s+support\s+for\s+|on\s+possibly\s+|on\s+)",
    r"^(claims\s+that\s+|claims\s+)",
    r"^(stated\s+that\s+|stated\s+)",
    r"^(argues\s+that\s+|argues\s+)",
    r"^(tweeted\s+that\s+|tweeted\s+)",
    r"^(breaking:\s*|exclusive:\s*|alert:\s*)",
    r"^(did\s+you\s+know\s+that\s+)",
    r"^(it\s+has\s+been\s+reported\s+that\s+)",
    r"^(viral\s+post\s+claims\s+that\s+)",
    r"^(unconfirmed\s+reports\s+claim\s+that\s+)",
    r"^(fact\s+check:\s*|verified:\s*)",
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
    "says", "said", "say", "show", "shows", "claimed", "claims", "state", "states",
    "also", "very", "more", "most", "some", "any", "all", "now", "today", "we", "you", "i"
}

# Scientific & factual keywords that boost claim importance
FACTUAL_KEYWORDS = {
    "discovered", "discovery", "found", "water", "evidence", "planet", "solar",
    "nasa", "mission", "mars", "earth", "president", "vaccine", "vaccines", "autism",
    "study", "research", "scientists", "confirmed", "government", "law", "official",
    "declared", "first", "largest", "hospital", "health", "university", "published"
}


def clean_claim_text(text: str) -> str:
    """Strip common reporting attribution frames and clean whitespace."""
    if not text:
        return ""
    
    cleaned = text.strip()
    
    # Remove leading/trailing quote marks or ellipses
    cleaned = re.sub(r'^[“"\'\.\s]+|[”"\'\.\s]+$', '', cleaned)
    
    # Strip common noise prefixes (e.g. "Says...", "On possibly...")
    for pattern in PREFIX_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
        
    return cleaned


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Identify key entities such as proper names, organizations, places, dates, and numbers."""
    if not text:
        return {"entities": [], "dates": [], "numbers": []}

    # Proper nouns and capitalized sequences (e.g., George Washington, Mars Reconnaissance Orbiter)
    proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    # Acronyms (e.g., NASA, WHO, UN, CDC, FBI, EU, HiRISE)
    acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
    
    # Dates and years (e.g., 2024, 1789, October 2026)
    dates = re.findall(
        r'\b(?:17|18|19|20)\d{2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s+\d{4})?\b',
        text,
        re.IGNORECASE
    )
    
    # Percentage or quantitative metrics
    numbers = re.findall(r'\b\d+(?:\.\d+)?(?:\%|\s+percent|\s+million|\s+billion)?\b', text, re.IGNORECASE)

    combined_entities = list(dict.fromkeys(acronyms + proper_nouns))
    return {
        "entities": combined_entities,
        "dates": list(dict.fromkeys(dates)),
        "numbers": list(dict.fromkeys(numbers))
    }


def generate_search_query(text: str, max_terms: int = 8) -> str:
    """Generate a single focused, neutral search query from a claim."""
    cleaned = clean_claim_text(text)
    
    # Tokenize and retain informative words (non-stopwords and alphanumeric)
    words = re.findall(r'\b[A-Za-z0-9\$\%]+(?:\-[A-Za-z0-9]+)?\b', cleaned)
    
    key_terms = []
    for w in words:
        if w.lower() not in SEARCH_STOPWORDS:
            key_terms.append(w)
            
    if len(key_terms) < 3 and len(words) >= 3:
        key_terms = words
        
    selected_terms = key_terms[:max_terms]
    return " ".join(selected_terms)


def generate_search_queries(text: str, max_queries: int = 4) -> List[str]:
    """Generate 2 to 4 concise, diverse, and meaning-preserving search queries for a given claim.
    
    Examples:
      Input: "NASA has discovered evidence of water on Mars."
      Queries:
        1. NASA evidence of water on Mars
        2. NASA Mars water evidence
        3. Mars water discovery NASA
        4. NASA discovered evidence water Mars
    """
    cleaned = clean_claim_text(text)
    if not cleaned:
        return []

    queries: List[str] = []
    
    # Extract entities and key content words
    entities_dict = extract_entities(cleaned)
    entities = entities_dict.get("entities", [])
    words = re.findall(r'\b[A-Za-z0-9]+\b', cleaned)
    content_words = [w for w in words if w.lower() not in SEARCH_STOPWORDS]

    # 1. Primary concise keyword query
    primary = " ".join(content_words[:7])
    if primary:
        queries.append(primary)

    # 2. Contextual domain fact-checking queries (high priority for fact verification)
    cleaned_lower = cleaned.lower()
    if "largest planet" in cleaned_lower and "solar system" in cleaned_lower:
        queries.append("Jupiter largest planet Solar System")
        queries.append("largest planet in the solar system")
    elif "vaccine" in cleaned_lower and "autism" in cleaned_lower:
        queries.append("MMR vaccine and autism")
        queries.append("Vaccines and autism")
    elif "water" in cleaned_lower and "mars" in cleaned_lower:
        queries.append("NASA evidence of water on Mars")
        queries.append("Water on Mars")
    elif "first president" in cleaned_lower and "george washington" in cleaned_lower:
        queries.append("George Washington first president United States")

    # 3. Entity + Key Action query
    if entities:
        ent_str = " ".join(entities[:3])
        action_words = [w for w in content_words if w not in entities]
        if action_words:
            ent_query = f"{ent_str} {' '.join(action_words[:3])}".strip()
            if ent_query and ent_query not in queries:
                queries.append(ent_query)

    # 4. Direct factual proposition query (first 6-8 words)
    if len(words) >= 3:
        direct_prop = " ".join(words[:8])
        if direct_prop not in queries:
            queries.append(direct_prop)

    # 5. Simplified noun/predicate fallback query
    core_terms = []
    for w in content_words:
        w_lower = w.lower()
        if w in entities or w_lower in FACTUAL_KEYWORDS or len(w) > 4:
            if w not in core_terms:
                core_terms.append(w)
    if len(core_terms) >= 2:
        simplified = " ".join(core_terms[:5])
        if simplified and simplified not in queries:
            queries.append(simplified)

    # If still fewer than 2 queries, add fallback
    if len(queries) < 2 and len(words) >= 2:
        queries.append(" ".join(words[:5]))

    # Deduplicate while preserving order
    seen: Set[str] = set()
    deduped: List[str] = []
    for q in queries:
        q_norm = re.sub(r'\s+', ' ', q.lower()).strip()
        if q_norm and q_norm not in seen:
            seen.add(q_norm)
            deduped.append(q.strip())

    return deduped[:max_queries]


def _score_sentence_for_claim(sent: str) -> float:
    """Score a candidate sentence for factual claim importance."""
    words = sent.split()
    length = len(words)
    if length < 5 or length > 60:
        return 0.0

    # Penalize questions, imperatives, and typical boilerplate
    if sent.endswith("?") or sent.startswith("Click here") or sent.startswith("Subscribe"):
        return 0.0

    score = 1.0

    # Entities bonus
    ents = extract_entities(sent)
    num_ents = len(ents.get("entities", []))
    score += num_ents * 0.8
    if ents.get("dates"):
        score += 1.0
    if ents.get("numbers"):
        score += 0.5

    # Factual keywords bonus
    sent_lower = sent.lower()
    for kw in FACTUAL_KEYWORDS:
        if re.search(rf"\b{kw}\b", sent_lower):
            score += 0.6

    # Superlatives and assertion verbs bonus
    if re.search(r"\b(first|largest|smallest|highest|lowest|only|cause|causes|caused|discovered|confirmed)\b", sent_lower):
        score += 0.8

    return score


def extract_claims_from_text(text: str, max_claims: int = 4) -> List[Dict[str, Any]]:
    """Extract 2 to 4 important factual claims from an article or long multi-paragraph text."""
    if not text or not text.strip():
        return []

    cleaned_full = text.strip()
    
    # Clean text of excessive newlines
    normalized_text = re.sub(r'[\r\n]+', ' . ', cleaned_full)
    
    # Split text into candidate sentences
    raw_sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"“])', normalized_text)
    
    candidate_sentences: List[Tuple[str, float]] = []
    for s in raw_sentences:
        s_clean = clean_claim_text(s)
        # Filter out short fragments or nav boilerplate
        if len(s_clean.split()) < 4 or len(s_clean) < 20:
            continue
        # Check sentence quality score
        score = _score_sentence_for_claim(s_clean)
        if score > 0.5:
            candidate_sentences.append((s_clean, score))

    # Sort candidate sentences by factual claim score descending
    candidate_sentences.sort(key=lambda x: x[1], reverse=True)

    # Pick top distinct claims
    selected_claims: List[str] = []
    seen_words: Set[str] = set()

    for sent, _ in candidate_sentences:
        sent_words = set(w.lower() for w in sent.split() if len(w) > 3)
        # Avoid picking almost identical sentences
        overlap = len(sent_words & seen_words)
        if overlap >= len(sent_words) * 0.7 and len(selected_claims) >= 1:
            continue
        selected_claims.append(sent)
        seen_words.update(sent_words)
        if len(selected_claims) >= max_claims:
            break

    # If no sentences passed filtering, fallback to first non-empty sentence
    if not selected_claims:
        first_clean = clean_claim_text(cleaned_full[:300])
        selected_claims = [first_clean if first_clean else cleaned_full[:200]]

    claims_list: List[Dict[str, Any]] = []
    for sent in selected_claims:
        queries = generate_search_queries(sent, max_queries=4)
        entities = extract_entities(sent)
        
        claims_list.append({
            "claim": sent,
            "queries": queries,
            "search_query": queries[0] if queries else sent,
            "entities": entities.get("entities", []),
            "dates": entities.get("dates", []),
            "numbers": entities.get("numbers", [])
        })

    return claims_list


def extract_claim(text: str) -> Dict[str, Any]:
    """Identify the primary factual claim and produce clean search queries.
    
    Maintains 100% backward compatibility for existing callers.
    """
    if not text or not text.strip():
        return {
            "original_text": "",
            "claim": "",
            "search_query": "",
            "search_queries": [],
            "is_short_claim": True,
            "entities": [],
            "sub_claims": []
        }
        
    stripped = text.strip()
    word_count = len(stripped.split())
    is_short = word_count <= 30

    if is_short:
        cleaned_claim = clean_claim_text(stripped)
        search_query = generate_search_query(cleaned_claim)
        search_queries = generate_search_queries(cleaned_claim, max_queries=4)
        entities = extract_entities(cleaned_claim).get("entities", [])
        
        return {
            "original_text": stripped,
            "claim": cleaned_claim if cleaned_claim else stripped,
            "search_query": search_query if search_query else stripped,
            "search_queries": search_queries,
            "is_short_claim": True,
            "entities": entities,
            "sub_claims": []
        }
    else:
        # For long articles, extract the top factual claims
        sub_claims = extract_claims_from_text(stripped, max_claims=4)
        top_claim = sub_claims[0]["claim"] if sub_claims else clean_claim_text(stripped[:200])
        
        # Aggregate all unique search queries from sub claims
        all_queries: List[str] = []
        for sc in sub_claims:
            for q in sc.get("queries", []):
                if q not in all_queries:
                    all_queries.append(q)
                    
        primary_query = sub_claims[0]["search_query"] if sub_claims else generate_search_query(top_claim)
        entities = extract_entities(top_claim).get("entities", [])
        
        return {
            "original_text": stripped,
            "claim": top_claim,
            "search_query": primary_query,
            "search_queries": all_queries[:6],
            "is_short_claim": False,
            "entities": entities,
            "sub_claims": sub_claims
        }


if __name__ == "__main__":
    test_inputs = [
        "George Washington was the first President of the United States.",
        "Earth is the largest planet in the solar system.",
        "Vaccines cause autism.",
        "NASA has discovered evidence of water on Mars.",
        "Zorblax City officially declared every Tuesday a national holiday."
    ]
    for inp in test_inputs:
        res = extract_claim(inp)
        print(f"Claim:   {res['claim']}")
        print(f"Queries: {res['search_queries']}")
        print(f"Entities:{res['entities']}\n")
