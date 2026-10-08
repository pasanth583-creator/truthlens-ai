import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

from pathlib import Path

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "production"
if not DEFAULT_MODEL_DIR.exists():
    DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "transformer"

class TransformerInference:
    def __init__(self, model_path: str = None):
        self.model_path = str(model_path or DEFAULT_MODEL_DIR)
        self.tokenizer = None
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
    def load(self):
        """Load the tokenizer and model from the saved directory."""
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
        self.model.to(self.device)
        self.model.eval()
        
    def predict_proba(self, text: str):
        """Return the class probabilities for the input text."""
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model is not loaded. Call load() first.")
            
        inputs = self.tokenizer(
            text, 
            return_tensors="pt", 
            padding=True, 
            truncation=True, 
            max_length=128
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)[0]
        
        class_probs = {}
        for idx, prob in enumerate(probs):
            label = self.model.config.id2label[idx]
            class_probs[label] = prob.item()
            
        return class_probs

    def predict(self, text: str):
        """Return the predicted label and confidence."""
        class_probs = self.predict_proba(text)
        predicted_label = max(class_probs, key=class_probs.get)
        confidence = class_probs[predicted_label]
        
        return {
            "label": predicted_label,
            "confidence": confidence,
            "probabilities": class_probs
        }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        text = sys.argv[1]
        from pathlib import Path
        model_dir = str(Path(__file__).resolve().parents[1] / "models" / "transformer")
        infer = TransformerInference(model_dir)
        infer.load()
        print(infer.predict(text))
