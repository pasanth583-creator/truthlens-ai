import sys
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.verification import verify_claim, synthesize_verification
from services.report_generator import generate_verification_report

REAL_TEST_CASES = [
    {
        "name": "REAL TEST 1: Model False/Misleading + Contradicting Evidence",
        "claim": "Scientific studies show that vaccines cause autism in children."
    },
    {
        "name": "REAL TEST 2: Model Reliable + Supporting Evidence",
        "claim": "George Washington was the first President of the United States."
    },
    {
        "name": "REAL TEST 3: Insufficient Evidence -> UNVERIFIED Status",
        "claim": "Obscure local town council committee passed municipal resolution 987654321xyz on Tuesday."
    },
    {
        "name": "REAL TEST 4: Low-Confidence Prediction Handling",
        "claim": "On possibly raising the Social Security retirement age."
    }
]

SYNTHETIC_LOGIC_FIXTURES = [
    {
        "name": "SYNTHETIC TEST A: Conflicting Signal (Model Reliable + Contradicting Evidence)",
        "pred_label": "Reliable",
        "confidence": 0.85,
        "evidence_status": "contradicting"
    },
    {
        "name": "SYNTHETIC TEST B: Conflicting Signal (Model False + Supporting Evidence)",
        "pred_label": "False",
        "confidence": 0.78,
        "evidence_status": "supporting"
    },
    {
        "name": "SYNTHETIC TEST C: Low Confidence + Contradicting Evidence",
        "pred_label": "False",
        "confidence": 0.42,
        "evidence_status": "contradicting"
    }
]


def run_real_tests():
    print("=" * 70)
    print("PART 1: REAL SYSTEM END-TO-END VERIFICATION TESTS")
    print("=" * 70)

    for tc in REAL_TEST_CASES:
        name = tc["name"]
        claim = tc["claim"]
        print(f"\n>>> RUNNING {name} <<<")
        result = verify_claim(claim)
        report = generate_verification_report(result)
        print(report)
        print("-" * 70)


def run_synthetic_tests():
    print("\n" + "=" * 70)
    print("PART 2: CONTROLLED SYNTHETIC LOGIC UNIT TESTS (DECISION MATRIX)")
    print("Note: These fixtures validate decision matrix edge cases without mocking live search.")
    print("=" * 70)

    for st in SYNTHETIC_LOGIC_FIXTURES:
        name = st["name"]
        pred = st["pred_label"]
        conf = st["confidence"]
        ev = st["evidence_status"]

        syn_res = synthesize_verification(pred_label=pred, confidence=conf, evidence_status=ev)
        print(f"\nFixture: {name}")
        print(f"  Inputs:  Model={pred} (Conf: {conf * 100:.0f}%), Evidence={ev.upper()}")
        print(f"  Status:  {syn_res['status']}")
        print(f"  Result:  \"{syn_res['result']}\"")
        print(f"  Conflict Detected: {syn_res['conflict_detected']}")
        print(f"  Low Conf Flag:     {syn_res['is_low_confidence']}")

    print("\n" + "=" * 70)
    print("ALL VERIFICATION ENGINE TESTS COMPLETE")
    print("=" * 70)


def main():
    run_real_tests()
    run_synthetic_tests()


if __name__ == "__main__":
    main()
