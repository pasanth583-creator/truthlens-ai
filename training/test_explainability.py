import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from services.explainer import explain_prediction, EXPLANATION_CONFIDENCE_THRESHOLD

TEST_CASES = [
    {
        "category": "1. Normal news claim",
        "text": "Under President George W. Bush, we added $4.9 trillion to the debt. Under President Obama weve added $6.5 trillion to the debt."
    },
    {
        "category": "2. Clearly suspicious/false example",
        "text": "Says George Washington said a free people should be armed to guard against government tyranny."
    },
    {
        "category": "3. Reliable example",
        "text": "Tennessee students now cover about 67 percent of the cost of their education at public universities, and some 60 percent at community colleges."
    },
    {
        "category": "4. Misleading example",
        "text": "Romneycare has killed 18,000 Massachusetts jobs."
    },
    {
        "category": "5. Short input",
        "text": "On possibly raising the Social Security retirement age."
    },
    {
        "category": "6. Longer input",
        "text": "After the 9/11 terrorist attacks grounded commercial air traffic, there was a temperature drop while the airplanes werent flying, for the week afterwards."
    }
]

def main():
    print("=" * 60)
    print("TRUTHLENS AI — EXPLAINABILITY ENGINE VERIFICATION SUITE")
    print("=" * 60)
    print(f"Configured Confidence Threshold: {EXPLANATION_CONFIDENCE_THRESHOLD * 100:.0f}%\n")

    for tc in TEST_CASES:
        category = tc["category"]
        text = tc["text"]
        print("-" * 60)
        print(f"TEST CASE: {category}")
        print(f"Input: \"{text}\"")
        
        result = explain_prediction(text)
        pred = result["prediction"]
        probs = result["probabilities"]
        exp = result["explanation"]
        
        print(f"Prediction: {pred['label']}")
        print(f"Confidence: {pred['confidence'] * 100:.2f}% (Status: {exp['confidence_status']})")
        print("Class probabilities:")
        for label, prob in probs.items():
            print(f"  - {label}: {prob * 100:.2f}%")
        
        print("Important phrases:")
        if exp["important_phrases"]:
            for item in exp["important_phrases"]:
                print(f"  - \"{item['phrase']}\" (Importance: {item['importance']:.2f}, Direction: {item['direction']})")
        else:
            print("  - None extracted")
            
        print(f"Explanation: {exp['summary']}")
        print()

    print("=" * 60)
    print("EXPLAINABILITY TESTS COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
