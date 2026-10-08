import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from services.claim_extractor import extract_claim
from services.evidence import search_evidence, WikipediaEvidenceProvider, GoogleFactCheckProvider

TEST_CLAIMS = [
    {
        "category": "1. Supporting Evidence Expected",
        "claim": "George Washington was the first President of the United States."
    },
    {
        "category": "2. Contradicting Evidence Expected",
        "claim": "Scientific studies show that vaccines cause autism in children."
    },
    {
        "category": "3. Insufficient Evidence Expected",
        "claim": "Obscure local town council committee passed municipal resolution 987654321xyz on Tuesday."
    }
]

def main():
    print("=" * 65)
    print("TRUTHLENS AI — EVIDENCE RETRIEVAL & VERIFICATION TEST SUITE")
    print("=" * 65)

    # Provider status check
    wiki_p = WikipediaEvidenceProvider()
    google_p = GoogleFactCheckProvider()
    
    print("PROVIDER STATUS:")
    print(f"  - {wiki_p.name}: {'AVAILABLE' if wiki_p.is_available() else 'UNAVAILABLE'}")
    print(f"  - {google_p.name}: {'AVAILABLE' if google_p.is_available() else 'UNAVAILABLE (Requires API Key)'}\n")

    for tc in TEST_CLAIMS:
        cat = tc["category"]
        raw_claim = tc["claim"]
        extracted = extract_claim(raw_claim)
        query = extracted["search_query"]

        print("-" * 65)
        print(f"TEST CATEGORY: {cat}")
        print(f"Claim:        \"{raw_claim}\"")
        print(f"Search query: \"{query}\"")

        res = search_evidence(raw_claim)
        status = res["evidence_status"]
        sources = res.get("sources", [])

        print(f"Evidence status: {status.upper()}")
        print(f"Summary:         {res['summary']}")
        print(f"Sources retrieved: {len(sources)}")

        if sources:
            for idx, s in enumerate(sources, 1):
                print(f"\n  [Source {idx}]")
                print(f"  Source title:    {s['title']}")
                print(f"  Source URL:      {s['url']}")
                print(f"  Source:          {s['source']}")
                print(f"  Snippet:         {s['snippet'][:140]}...")
                print(f"  Relation:        {s['relation']}")
                print(f"  Relevance score: {s['relevance_score']:.2f}")
        else:
            print("  (No sources retrieved — safe fallback triggered without placeholder URLs)")

        print()

    print("=" * 65)
    print("EVIDENCE RETRIEVAL SUITE COMPLETE")
    print("=" * 65)

if __name__ == "__main__":
    main()
