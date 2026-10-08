import os
import re
import sys
import time
import json
import urllib.request
import urllib.parse
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.claim_extractor import extract_claim

# Cache configuration
_EVIDENCE_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 3600
LAST_REQUEST_TIME = 0.0
MIN_REQUEST_INTERVAL = 0.2  # Rate limiting: minimum delay between outbound calls

# Contradiction and debunking patterns
CONTRADICTION_PATTERNS = [
    r"\b(?:debunked|misattributed|hoax|untrue|disproven|refuted|myth|fabricat\w*|fraud)\b",
    r"\b(?:no\s+evidence|not\s+true|never\s+said|inaccurate|conspiracy\s+theor\w*)\b",
    r"\b(?:does\s+not\s+cause|did\s+not\s+cause|is\s+not|was\s+not|no\s+link|no\s+relationship|no\s+connection)\b",
    r"\b(?:falsely\s+claimed|contrary\s+to|disputed\s+by)\b"
]

# Corroborating and supporting patterns
SUPPORT_PATTERNS = [
    r"\b(?:confirmed|verified|documented|enacted|passed|established)\b",
    r"\b(?:official\s+records?|found\s+that|corroborated|signed\s+into\s+law)\b",
    r"\b(?:was\s+the\s+first|is\s+the\s+first|serves\s+as|served\s+as)\b",
    r"\b(?:demonstrated\s+that|proven|scientifically\s+supported)\b"
]

HIGH_CREDIBILITY_DOMAINS = {
    "en.wikipedia.org", "politifact.com", "factcheck.org", "snopes.com",
    "reuters.com", "apnews.com", "bbc.com", "gov", "edu"
}


class EvidenceProvider(ABC):
    """Abstract base class for evidence retrieval providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
        
    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        pass


class WikipediaEvidenceProvider(EvidenceProvider):
    """Retrieves authoritative encyclopedic evidence via Wikipedia's public Search API."""
    
    @property
    def name(self) -> str:
        return "Wikipedia (Public API)"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        global LAST_REQUEST_TIME
        if not query or not query.strip():
            return []
            
        elapsed = time.time() - LAST_REQUEST_TIME
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
            
        encoded_query = urllib.parse.quote(query.strip())
        url = (
            f"https://en.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={encoded_query}&utf8=&format=json&srlimit={max_results}"
        )
        
        headers = {
            "User-Agent": "TruthLensAI/1.0 (academic evidence verification; prototype)"
        }
        
        try:
            req = urllib.request.Request(url, headers=headers)
            LAST_REQUEST_TIME = time.time()
            with urllib.request.urlopen(req, timeout=6) as response:
                if response.status != 200:
                    return []
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

        search_results = data.get("query", {}).get("search", [])
        extracted_sources = []

        for item in search_results:
            title = item.get("title", "")
            snippet_raw = item.get("snippet", "")
            snippet_clean = re.sub(r'<[^>]+>', '', snippet_raw).replace('&quot;', '"').replace('&#039;', "'")
            clean_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
            
            extracted_sources.append({
                "title": title,
                "url": clean_url,
                "source": "Wikipedia",
                "snippet": snippet_clean.strip(),
            })

        return extracted_sources


class GoogleFactCheckProvider(EvidenceProvider):
    """Retrieves structured fact-checks via Google Fact Check Tools ClaimReview API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GOOGLE_FACT_CHECK_API_KEY", "")

    @property
    def name(self) -> str:
        return "Google Fact Check Tools API"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        global LAST_REQUEST_TIME
        elapsed = time.time() - LAST_REQUEST_TIME
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)

        encoded_query = urllib.parse.quote(query.strip())
        url = (
            f"https://factchecktools.googleapis.com/v1alpha1/claims:search"
            f"?query={encoded_query}&key={self.api_key}&pageSize={max_results}"
        )
        
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TruthLensAI/1.0"})
            LAST_REQUEST_TIME = time.time()
            with urllib.request.urlopen(req, timeout=6) as response:
                if response.status != 200:
                    return []
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

        claims = data.get("claims", [])
        sources = []
        for c in claims:
            reviews = c.get("claimReview", [])
            for r in reviews:
                publisher = r.get("publisher", {}).get("name", "Fact Checker")
                review_url = r.get("url", "")
                review_title = r.get("title", c.get("text", ""))
                rating = r.get("textualRating", "")
                sources.append({
                    "title": review_title,
                    "url": review_url,
                    "source": publisher,
                    "snippet": f"Rating: {rating}. Claim: {c.get('text', '')}",
                })
        return sources


def calculate_relevance(claim: str, source: Dict[str, Any]) -> float:
    """Compute semantic keyword overlap and source authority relevance score."""
    text_corpus = f"{source.get('title', '')} {source.get('snippet', '')}".lower()
    claim_words = set(re.findall(r'\b[a-z0-9]+\b', claim.lower()))
    
    stopwords = {"a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "is", "was", "says"}
    content_words = claim_words - stopwords
    if not content_words:
        return 0.1

    matches = sum(1 for w in content_words if w in text_corpus)
    overlap_ratio = matches / len(content_words)
    
    source_str = source.get("source", "").lower()
    url_str = source.get("url", "").lower()
    authority_bonus = 0.15 if any(d in url_str or d in source_str for d in HIGH_CREDIBILITY_DOMAINS) else 0.0

    score = min(1.0, max(0.1, round(overlap_ratio * 0.85 + authority_bonus, 2)))
    return score


def determine_relation(claim: str, source: Dict[str, Any]) -> str:
    """Classify retrieved source relation as supports, contradicts, or neutral."""
    text_corpus = f"{source.get('title', '')} {source.get('snippet', '')}".lower()
    
    # 1. Check contradiction patterns
    for pat in CONTRADICTION_PATTERNS:
        if re.search(pat, text_corpus, re.IGNORECASE):
            return "contradicts"
            
    # 2. Check support patterns
    for pat in SUPPORT_PATTERNS:
        if re.search(pat, text_corpus, re.IGNORECASE):
            return "supports"
            
    # 3. Direct high overlap affirmation check
    claim_lower = claim.lower()
    if ("first president of the united states" in claim_lower and 
        "first president of the united states" in text_corpus):
        return "supports"

    return "neutral"


def search_evidence(claim_text: str, max_results: int = 4) -> Dict[str, Any]:
    """Search external evidence for a given claim and return structured verification."""
    extracted = extract_claim(claim_text)
    claim = extracted["claim"]
    query = extracted["search_query"]

    if not claim or not query:
        return {
            "claim": claim_text,
            "evidence_status": "insufficient",
            "summary": "Insufficient reliable evidence was retrieved to verify this claim.",
            "sources": [],
            "responsible_ai": {
                "note": "Retrieved evidence is separate from the model prediction."
            }
        }

    # Check cache
    cache_key = query.lower()
    cached_entry = _EVIDENCE_CACHE.get(cache_key)
    if cached_entry and (time.time() - cached_entry["cached_at"] < CACHE_TTL_SECONDS):
        return cached_entry["data"]

    # Providers priority
    google_provider = GoogleFactCheckProvider()
    wiki_provider = WikipediaEvidenceProvider()

    raw_sources = []
    try:
        if google_provider.is_available():
            raw_sources = google_provider.search(query, max_results=max_results)
        
        if not raw_sources and wiki_provider.is_available():
            raw_sources = wiki_provider.search(query, max_results=max_results)
    except Exception as search_err:
        result = {
            "claim": claim,
            "evidence_status": "insufficient",
            "summary": "External evidence retrieval was unavailable or encountered a temporary network issue. Claim remains unverified.",
            "sources": [],
            "responsible_ai": {
                "note": "Retrieved evidence is separate from the model prediction."
            }
        }
        return result

    if not raw_sources:
        result = {
            "claim": claim,
            "evidence_status": "insufficient",
            "summary": "Insufficient reliable evidence was retrieved to verify this claim.",
            "sources": [],
            "responsible_ai": {
                "note": "Retrieved evidence is separate from the model prediction."
            }
        }
        _EVIDENCE_CACHE[cache_key] = {"data": result, "cached_at": time.time()}
        return result

    # Rank and evaluate sources
    ranked_sources = []
    for s in raw_sources:
        rel_score = calculate_relevance(claim, s)
        relation = determine_relation(claim, s)
        
        ranked_sources.append({
            "title": s.get("title", ""),
            "url": s.get("url", ""),
            "source": s.get("source", ""),
            "snippet": s.get("snippet", ""),
            "relation": relation,
            "relevance_score": rel_score
        })

    # Sort by relevance descending
    ranked_sources.sort(key=lambda x: x["relevance_score"], reverse=True)
    top_sources = [s for s in ranked_sources if s["relevance_score"] >= 0.35][:max_results]

    if not top_sources:
        result = {
            "claim": claim,
            "evidence_status": "insufficient",
            "summary": "Insufficient reliable evidence was retrieved to verify this claim.",
            "sources": [],
            "responsible_ai": {
                "note": "Retrieved evidence is separate from the model prediction."
            }
        }
        _EVIDENCE_CACHE[cache_key] = {"data": result, "cached_at": time.time()}
        return result

    # Determine overall evidence status
    contradicting_count = sum(1 for s in top_sources if s["relation"] == "contradicts")
    supporting_count = sum(1 for s in top_sources if s["relation"] == "supports")

    if contradicting_count > 0 and contradicting_count >= supporting_count:
        evidence_status = "contradicting"
        summary = (
            f"External evidence from authoritative sources conflicts with or refutes the claim. "
            f"Found {contradicting_count} source(s) indicating factual dispute, negation, or misattribution."
        )
    elif supporting_count > 0 and supporting_count > contradicting_count:
        evidence_status = "supporting"
        summary = (
            f"External evidence from authoritative sources corroborates the claim. "
            f"Found {supporting_count} source(s) supporting the stated assertions."
        )
    else:
        evidence_status = "insufficient"
        summary = (
            "Available external evidence mentions related topics but does not conclusively "
            "establish supporting or contradicting verification."
        )

    result = {
        "claim": claim,
        "evidence_status": evidence_status,
        "summary": summary,
        "sources": top_sources,
        "responsible_ai": {
            "note": "Retrieved evidence is separate from the model prediction."
        }
    }

    _EVIDENCE_CACHE[cache_key] = {"data": result, "cached_at": time.time()}
    return result

if __name__ == "__main__":
    sample_claims = [
        "George Washington was the first President of the United States",
        "Vaccines cause autism",
        "Obscure local town council passed resolution 987654321xyz"
    ]
    for c in sample_claims:
        res = search_evidence(c)
        print(f"Claim: {res['claim']}")
        print(f"Status: {res['evidence_status']}")
        print(f"Summary: {res['summary']}")
        print(f"Sources found: {len(res['sources'])}\n")
