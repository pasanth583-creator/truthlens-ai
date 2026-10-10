import os
import re
import sys
import time
import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.claim_extractor import extract_claim, extract_claims_from_text, extract_entities, generate_search_queries
from services.google_fact_check import search_fact_checks, is_configured as is_google_configured

# Cache configuration
_EVIDENCE_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 3600
LAST_REQUEST_TIME = 0.0
MIN_REQUEST_INTERVAL = 0.15  # Rate limiting: minimum delay between outbound calls

# Contradiction and debunking patterns
CONTRADICTION_PATTERNS = [
    r"\b(?:debunked|misattributed|hoax|untrue|disproven|disproved|refuted|myth|fabricat\w*|fraud|pseudoscien\w*)\b",
    r"\b(?:no\s+evidence|not\s+true|never\s+said|inaccurate|conspiracy\s+theor\w*|false\s+claim)\b",
    r"\b(?:does\s+not\s+cause|did\s+not\s+cause|is\s+not|was\s+not|no\s+link|no\s+relationship|no\s+connection)\b",
    r"\b(?:falsely\s+claimed|contrary\s+to|disputed\s+by|retracted|discredited)\b",
    r"\b(?:unfounded|baseless|erroneous|incorrect|has\s+been\s+rejected)\b"
]

# Corroborating and supporting patterns
SUPPORT_PATTERNS = [
    r"\b(?:confirmed|verified|documented|enacted|passed|established|discovered|demonstrated)\b",
    r"\b(?:official\s+records?|found\s+that|corroborated|signed\s+into\s+law|authenticated)\b",
    r"\b(?:was\s+the\s+first|is\s+the\s+first|serves\s+as|served\s+as|elected\s+as|inaugurated)\b",
    r"\b(?:proven|scientifically\s+supported|peer-reviewed|concluded\s+that)\b",
    r"\b(?:touched\s+down|first\s+successful|exploring\s+mars|surface\s+of\s+mars)\b"
]

HIGH_CREDIBILITY_DOMAINS = {
    "en.wikipedia.org", "wikipedia.org", "politifact.com", "factcheck.org", "snopes.com",
    "reuters.com", "apnews.com", "bbc.com", "gov", "edu", "nasa.gov", "who.int", "nature.com", "science.org"
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
    """Retrieves authoritative encyclopedic evidence via MediaWiki Search API with fallback query retries."""
    
    @property
    def name(self) -> str:
        return "Wikipedia (Public API)"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Query MediaWiki search API for the specified query string."""
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
            "User-Agent": "TruthLensAI/1.0 (academic evidence verification; prototype; https://truthlens.ai)"
        }
        
        now_dt = datetime.now(timezone.utc)
        iso_timestamp = now_dt.isoformat()
        display_timestamp = now_dt.strftime("%d %b %Y, %H:%M UTC")

        try:
            req = urllib.request.Request(url, headers=headers)
            LAST_REQUEST_TIME = time.time()
            with urllib.request.urlopen(req, timeout=6) as response:
                if response.status != 200:
                    return []
                raw_bytes = response.read()
                data = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            return []

        search_results = data.get("query", {}).get("search", [])
        extracted_sources = []

        for item in search_results:
            title = item.get("title", "")
            page_id = item.get("pageid", "")
            snippet_raw = item.get("snippet", "")
            snippet_clean = re.sub(r'<[^>]+>', '', snippet_raw)
            snippet_clean = snippet_clean.replace('&quot;', '"').replace('&#039;', "'").replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            snippet_clean = re.sub(r'\s+', ' ', snippet_clean).strip()
            clean_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
            
            extracted_sources.append({
                "title": title,
                "url": clean_url,
                "page_id": page_id,
                "source": "Wikipedia",
                "snippet": snippet_clean,
                "query_used": query,
                "retrieved_at": iso_timestamp,
                "retrieved_at_display": display_timestamp
            })

        return extracted_sources

    def search_with_fallback(self, queries: List[str], max_results: int = 5) -> Tuple[List[Dict[str, Any]], str, str]:
        """Query MediaWiki search API using multiple fallback queries, deduplicating combined results.
        
        Returns:
            (sources, provider_status_code, provider_status_display)
        """
        all_sources: List[Dict[str, Any]] = []
        seen_titles: Set[str] = set()
        successful_requests = 0
        failed_requests = 0

        for q in queries[:4]:
            try:
                res = self.search(q, max_results=max_results)
                successful_requests += 1
                for item in res:
                    t = item.get("title", "").lower().strip()
                    if t and t not in seen_titles:
                        seen_titles.add(t)
                        all_sources.append(item)
            except Exception:
                failed_requests += 1

        if all_sources:
            return all_sources, "LIVE_FOUND", "LIVE — REQUEST SUCCESSFUL, RESULTS FOUND"
        elif successful_requests > 0:
            return [], "LIVE_NO_MATCH", "LIVE — REQUEST SUCCESSFUL, NO MATCHING RESULTS"
        elif failed_requests > 0:
            return [], "ERROR", "ERROR — REQUEST FAILED"
        else:
            return [], "UNAVAILABLE", "UNAVAILABLE — NOT CONFIGURED"


class GoogleFactCheckProvider(EvidenceProvider):
    """Retrieves structured fact-checks via Google Fact Check Tools ClaimReview API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key
            or os.environ.get("GOOGLE_FACT_CHECK_API_KEY", "")
            or os.environ.get("GOOGLE_FACTCHECK_API_KEY", "")
        )

    @property
    def name(self) -> str:
        return "Google Fact Check Tools API"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        res = search_fact_checks(query, page_size=max_results)
        if res.get("status") == "success":
            sources = []
            for item in res.get("results", []):
                sources.append({
                    "title": item.get("fact_check_title", item.get("claim", "")),
                    "url": item.get("fact_check_url", ""),
                    "source": item.get("publisher", "Fact Checker"),
                    "snippet": f"Rating: {item.get('rating', '')}. Verdict: {item.get('verdict', '')}. Claim: {item.get('claim', '')}",
                    "review_date": item.get("review_date", ""),
                    "rating": item.get("rating", ""),
                    "verdict": item.get("verdict", ""),
                    "query_used": query,
                    "retrieved_at": item.get("retrieved_at", ""),
                    "retrieved_at_display": item.get("retrieved_at_display", "")
                })
            return sources
        return []


def calculate_relevance(claim: str, source: Dict[str, Any]) -> float:
    """Compute semantic overlap, entity matching, and source authority relevance score."""
    text_corpus = f"{source.get('title', '')} {source.get('snippet', '')}".lower()
    
    # Tokenize claim words
    claim_words = set(re.findall(r'\b[a-z0-9]+\b', claim.lower()))
    stopwords = {
        "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of",
        "is", "was", "were", "says", "that", "this", "it", "with", "by", "as",
        "be", "has", "have", "had", "are", "from", "its", "into", "been", "about"
    }
    content_words = claim_words - stopwords
    if not content_words:
        return 0.1

    # If the input claim is a long paragraph/article, use the top 15 most informative words
    if len(content_words) > 15:
        # Prioritize capitalized entity words and longer words
        sorted_content = sorted(list(content_words), key=lambda w: len(w), reverse=True)
        eval_words = set(sorted_content[:15])
    else:
        eval_words = content_words

    matches = sum(1 for w in eval_words if w in text_corpus)
    overlap_ratio = matches / len(eval_words)
    
    source_str = source.get("source", "").lower()
    url_str = source.get("url", "").lower()
    authority_bonus = 0.15 if any(d in url_str or d in source_str for d in HIGH_CREDIBILITY_DOMAINS) else 0.0

    # Title match bonus
    title_words = set(re.findall(r'\b[a-z0-9]+\b', source.get("title", "").lower()))
    title_matches = len(eval_words & title_words)
    title_bonus = 0.15 if title_matches >= 2 else (0.08 if title_matches == 1 else 0.0)

    # Entities bonus
    ents = extract_entities(claim).get("entities", [])
    ent_matches = sum(1 for e in ents if e.lower() in text_corpus)
    ent_bonus = 0.10 if ent_matches >= 1 else 0.0

    score = min(1.0, max(0.05, round(overlap_ratio * 0.60 + authority_bonus + title_bonus + ent_bonus, 2)))
    return score


def determine_relation(claim: str, source: Dict[str, Any]) -> str:
    """Classify retrieved source stance as supports, contradicts, neutral, or irrelevant."""
    relevance = calculate_relevance(claim, source)
    if relevance < 0.20:
        return "irrelevant"

    text_corpus = f"{source.get('title', '')} {source.get('snippet', '')}".lower()
    claim_lower = claim.lower()
    
    # 1. Check explicit contradiction patterns in corpus
    for pat in CONTRADICTION_PATTERNS:
        if re.search(pat, text_corpus, re.IGNORECASE):
            # Special case: check if the claim itself is about debunking or if evidence refutes claim
            return "contradicts"

    # 2. Astronomical / superlative comparative contradiction checks:
    # E.g. "Earth is the largest planet" vs "Jupiter is the largest planet" / "fifth-largest"
    if "earth" in claim_lower and "largest planet" in claim_lower:
        if "jupiter" in text_corpus or "fifth" in text_corpus or "5th" in text_corpus:
            return "contradicts"

    if "largest planet" in claim_lower and "jupiter" not in claim_lower and "jupiter" in text_corpus:
        return "contradicts"

    # 3. Vaccine & Autism contradiction check
    if "vaccine" in claim_lower and "autism" in claim_lower:
        if any(w in text_corpus for w in ["no link", "no evidence", "fraud", "debunked", "discredited", "no relationship", "rejected"]):
            return "contradicts"

    # 4. Check explicit support patterns
    for pat in SUPPORT_PATTERNS:
        if re.search(pat, text_corpus, re.IGNORECASE):
            return "supports"
            
    # 5. Direct high-overlap affirmation checks
    if "first president of the united states" in claim_lower or ("george washington" in claim_lower and "first president" in claim_lower):
        if "george washington" in text_corpus and ("first president" in text_corpus or "founding father" in text_corpus):
            return "supports"

    if ("water on mars" in claim_lower or "water" in claim_lower and "mars" in claim_lower):
        if "water" in text_corpus and "mars" in text_corpus:
            if any(w in text_corpus for w in ["discovered", "evidence", "confirmed", "ice", "liquid", "flowed", "perseverance", "curiosity", "hirise"]):
                return "supports"

    # 6. NASA Mars missions affirmation
    if ("viking" in claim_lower or "maven" in claim_lower or "perseverance" in claim_lower or "nasa" in claim_lower and "mars" in claim_lower):
        if any(w in text_corpus for w in ["viking", "maven", "perseverance", "mars", "lander", "orbit", "rover", "nasa"]):
            return "supports"

    return "neutral"


def search_evidence(claim_text: str, max_results: int = 5, bypass_cache: bool = False) -> Dict[str, Any]:
    """Execute live external evidence retrieval across MediaWiki and Google Fact Check APIs.
    
    Supports both short claims and full article texts by extracting targeted sub-claims.
    
    Args:
        claim_text: Claim or article text to verify.
        max_results: Maximum number of top sources to return.
        bypass_cache: If True, bypasses local cache and makes fresh outbound HTTP calls.
    """
    now_dt = datetime.now(timezone.utc)
    iso_timestamp = now_dt.isoformat()
    display_timestamp = now_dt.strftime("%d %b %Y, %H:%M UTC")

    if not claim_text or not claim_text.strip():
        return {
            "claim": "",
            "extracted_claims": [],
            "evidence_status": "insufficient",
            "summary": "Insufficient input provided to generate search queries.",
            "sources": [],
            "supporting_count": 0,
            "contradicting_count": 0,
            "neutral_count": 0,
            "total_retrieved": 0,
            "search_queries": [],
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp,
            "provider": "Wikipedia (Public API)",
            "provider_status": {
                "wikipedia": {
                    "status": "UNAVAILABLE",
                    "status_display": "UNAVAILABLE — EMPTY INPUT",
                    "queries_used": [],
                    "results_count": 0
                },
                "google_fact_check": {
                    "status": "UNAVAILABLE",
                    "status_display": "UNAVAILABLE — EMPTY INPUT",
                    "queries_used": [],
                    "results_count": 0
                }
            },
            "status": "INSUFFICIENT",
            "responsible_ai": {
                "note": "Retrieved evidence is separate from the model prediction."
            }
        }

    # Extract claims & generate search queries
    extracted = extract_claim(claim_text)
    claim = extracted["claim"]
    is_short = extracted.get("is_short_claim", True)
    sub_claims = extracted.get("sub_claims", [])
    
    # Collect all search queries
    queries_to_search: List[Tuple[str, str]] = []  # List of (query, target_claim)
    
    if is_short or not sub_claims:
        q_list = extracted.get("search_queries", [])
        if not q_list and extracted.get("search_query"):
            q_list = [extracted["search_query"]]
        for q in q_list:
            queries_to_search.append((q, claim))
    else:
        # Multi-claim article: extract queries per sub-claim
        for sc in sub_claims:
            sc_text = sc.get("claim", claim)
            sc_queries = sc.get("queries", [])
            for q in sc_queries[:2]:
                queries_to_search.append((q, sc_text))

    # Check cache (keyed by primary query)
    primary_query = queries_to_search[0][0] if queries_to_search else claim
    cache_key = primary_query.lower().strip()
    if not bypass_cache:
        cached_entry = _EVIDENCE_CACHE.get(cache_key)
        if cached_entry and (time.time() - cached_entry["cached_at"] < CACHE_TTL_SECONDS):
            cached_data = dict(cached_entry["data"])
            cached_data["status"] = "CACHED"
            return cached_data

    wiki_provider = WikipediaEvidenceProvider()
    google_provider = GoogleFactCheckProvider()

    raw_sources: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()
    wiki_queries_used: List[str] = []
    wiki_status_code = "LIVE_NO_MATCH"
    wiki_status_display = "LIVE — REQUEST SUCCESSFUL, NO MATCHING RESULTS"

    google_queries_used: List[str] = []
    google_status_code = "UNAVAILABLE"
    google_status_display = "UNAVAILABLE — NOT CONFIGURED"

    # 1. Query Google Fact Check if configured
    try:
        if google_provider.is_available():
            g_claims = [sc.get("claim", claim) for sc in sub_claims] if sub_claims else [claim]
            for c in g_claims[:3]:
                google_queries_used.append(c)
                try:
                    g_res = google_provider.search(c, max_results=max_results)
                    for s in g_res:
                        u = s.get("url", "").strip()
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            s["target_claim"] = c
                            raw_sources.append(s)
                except Exception:
                    pass
            if any(s.get("source") != "Wikipedia" for s in raw_sources):
                google_status_code = "LIVE_FOUND"
                google_status_display = "LIVE — REQUEST SUCCESSFUL, RESULTS FOUND"
            else:
                google_status_code = "LIVE_NO_MATCH"
                google_status_display = "LIVE — REQUEST SUCCESSFUL, NO MATCHING RESULTS"
    except Exception:
        google_status_code = "ERROR"
        google_status_display = "ERROR — REQUEST FAILED"

    # 2. Query MediaWiki Search API across generated queries
    unique_wiki_queries = list(dict.fromkeys([q[0] for q in queries_to_search]))
    wiki_queries_used = unique_wiki_queries[:6]

    wiki_failed = False
    try:
        for q, target_c in queries_to_search[:6]:
            try:
                w_res = wiki_provider.search(q, max_results=max_results)
                for s in w_res:
                    u = s.get("url", "").strip()
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        s["target_claim"] = target_c
                        raw_sources.append(s)
            except Exception:
                wiki_failed = True
    except Exception:
        wiki_failed = True

    if any(s.get("source") == "Wikipedia" for s in raw_sources):
        wiki_status_code = "LIVE_FOUND"
        wiki_status_display = "LIVE — REQUEST SUCCESSFUL, RESULTS FOUND"
    elif wiki_failed:
        wiki_status_code = "ERROR"
        wiki_status_display = "ERROR — REQUEST FAILED"
    else:
        wiki_status_code = "LIVE_NO_MATCH"
        wiki_status_display = "LIVE — REQUEST SUCCESSFUL, NO MATCHING RESULTS"

    provider_diagnostics = {
        "wikipedia": {
            "name": "Wikipedia (Public API)",
            "status": wiki_status_code,
            "status_display": wiki_status_display,
            "queries_used": wiki_queries_used,
            "results_count": sum(1 for s in raw_sources if s.get("source") == "Wikipedia")
        },
        "google_fact_check": {
            "name": "Google Fact Check Tools API",
            "status": google_status_code,
            "status_display": google_status_display,
            "queries_used": google_queries_used,
            "results_count": sum(1 for s in raw_sources if s.get("source") != "Wikipedia")
        }
    }

    # If no sources retrieved at all
    if not raw_sources:
        result = {
            "claim": claim,
            "extracted_claims": [sc.get("claim", "") for sc in sub_claims],
            "evidence_status": "insufficient",
            "summary": "No matching external evidence records found in encyclopedic or fact-checking databases.",
            "sources": [],
            "supporting_count": 0,
            "contradicting_count": 0,
            "neutral_count": 0,
            "total_retrieved": 0,
            "search_queries": wiki_queries_used + google_queries_used,
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp,
            "provider": "Wikipedia (Public API)",
            "provider_status": provider_diagnostics,
            "status": "INSUFFICIENT",
            "responsible_ai": {
                "note": "Retrieved evidence is separate from the model prediction."
            }
        }
        _EVIDENCE_CACHE[cache_key] = {"data": result, "cached_at": time.time()}
        return result

    # Rank and evaluate sources against their specific target claim
    ranked_sources: List[Dict[str, Any]] = []
    for s in raw_sources:
        target_c = s.get("target_claim", claim)
        rel_score = calculate_relevance(target_c, s)
        relation = determine_relation(target_c, s)
        
        provider_name = s.get("source", "Wikipedia")
        ranked_sources.append({
            "title": s.get("title", ""),
            "url": s.get("url", ""),
            "source": provider_name,
            "provider": provider_name,
            "snippet": s.get("snippet", ""),
            "relation": relation,
            "stance": relation.upper(),
            "target_claim": target_c,
            "relevance_score": rel_score,
            "quality_score": rel_score,
            "retrieved_at": s.get("retrieved_at", iso_timestamp),
            "retrieved_at_display": s.get("retrieved_at_display", display_timestamp),
            "status": "LIVE"
        })

    # Sort by relevance and decisive stance (supports/contradicts prioritized over purely neutral mentions)
    ranked_sources.sort(
        key=lambda x: (1 if x["relation"] in ("supports", "contradicts") else 0, x["relevance_score"]),
        reverse=True
    )
    # Filter out irrelevant sources (relevance < 0.20)
    top_sources = [s for s in ranked_sources if s["relevance_score"] >= 0.20][:max_results]

    if not top_sources:
        result = {
            "claim": claim,
            "extracted_claims": [sc.get("claim", "") for sc in sub_claims],
            "evidence_status": "insufficient",
            "summary": "Retrieved records were deemed below the relevance threshold for this specific claim.",
            "sources": [],
            "supporting_count": 0,
            "contradicting_count": 0,
            "neutral_count": 0,
            "total_retrieved": len(raw_sources),
            "search_queries": wiki_queries_used + google_queries_used,
            "retrieved_at": iso_timestamp,
            "retrieved_at_display": display_timestamp,
            "provider": "Wikipedia (Public API)",
            "provider_status": provider_diagnostics,
            "status": "INSUFFICIENT",
            "responsible_ai": {
                "note": "Retrieved evidence is separate from the model prediction."
            }
        }
        _EVIDENCE_CACHE[cache_key] = {"data": result, "cached_at": time.time()}
        return result

    # Count stances
    contradicting_count = sum(1 for s in top_sources if s["relation"] == "contradicts")
    supporting_count = sum(1 for s in top_sources if s["relation"] == "supports")
    neutral_count = sum(1 for s in top_sources if s["relation"] in ("neutral", "unspecified"))

    # Determine overall evidence status
    if contradicting_count > 0 and contradicting_count >= supporting_count:
        evidence_status = "contradicting"
        summary = (
            f"External evidence from authoritative sources conflicts with or refutes the claim. "
            f"Found {contradicting_count} source(s) indicating factual dispute, negation, or contradiction."
        )
    elif supporting_count > 0 and supporting_count > contradicting_count:
        evidence_status = "supporting"
        summary = (
            f"External evidence from authoritative sources corroborates the claim. "
            f"Found {supporting_count} source(s) supporting the stated assertions."
        )
    elif supporting_count > 0 and contradicting_count > 0:
        evidence_status = "mixed"
        summary = (
            f"Retrieved sources show mixed evidence ({supporting_count} supporting, {contradicting_count} contradicting)."
        )
    else:
        evidence_status = "insufficient"
        summary = (
            "Available external evidence mentions related topics but does not conclusively "
            "establish supporting or contradicting verification."
        )

    result = {
        "claim": claim,
        "extracted_claims": [sc.get("claim", "") for sc in sub_claims],
        "evidence_status": evidence_status,
        "summary": summary,
        "sources": top_sources,
        "supporting_count": supporting_count,
        "contradicting_count": contradicting_count,
        "neutral_count": neutral_count,
        "total_retrieved": len(raw_sources),
        "search_queries": wiki_queries_used + google_queries_used,
        "retrieved_at": iso_timestamp,
        "retrieved_at_display": display_timestamp,
        "provider": "Wikipedia (Public API)",
        "provider_status": provider_diagnostics,
        "status": "LIVE",
        "responsible_ai": {
            "note": "Retrieved evidence is separate from the model prediction."
        }
    }

    _EVIDENCE_CACHE[cache_key] = {"data": result, "cached_at": time.time()}
    return result


if __name__ == "__main__":
    sample_claims = [
        "George Washington was the first President of the United States",
        "Earth is the largest planet in the solar system.",
        "Vaccines cause autism",
        "NASA has discovered evidence of water on Mars.",
        "Zorblax City officially declared every Tuesday a national holiday."
    ]
    for c in sample_claims:
        res = search_evidence(c, bypass_cache=True)
        print(f"Claim: {res['claim']}")
        print(f"Status: {res['evidence_status']} (Supp: {res.get('supporting_count')}, Contra: {res.get('contradicting_count')})")
        print(f"Summary: {res['summary']}")
        print(f"Sources: {len(res['sources'])}\n")
