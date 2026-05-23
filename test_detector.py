"""Phase 1: standalone CLI that runs SigLIP inference on a local image.

Run: `python test_detector.py path/to/image.jpg`
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoImageProcessor, SiglipForImageClassification

MODEL_ID = "Ateeqq/ai-vs-human-image-detector"

# Maps raw model labels (whatever id2label returns) to display strings.
# Ateeqq/ai-vs-human-image-detector uses short codes like "ai" / "hum".
_DISPLAY = {"ai": "AI-Generated", "hum": "Human", "human": "Human"}


def pick_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _display_label(raw: str) -> str:
    key = raw.strip().lower()
    if key not in _DISPLAY:
        raise RuntimeError(
            f"Unknown raw label {raw!r} from model.config.id2label; "
            f"update _DISPLAY in test_detector.py (known: {sorted(_DISPLAY)})"
        )
    return _DISPLAY[key]


def detect(image_path: str, processor, model, device: torch.device) -> tuple[str, float]:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"No such image: {image_path}")
    try:
        image = Image.open(path).convert("RGB")
    except Exception as e:
        raise ValueError(f"Could not open {image_path} as an image: {e}") from e

    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0]
    top_idx = int(torch.argmax(probs).item())
    confidence = float(probs[top_idx].item())
    raw_label = model.config.id2label[top_idx]
    return _display_label(raw_label), confidence


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python test_detector.py <image_path>", file=sys.stderr)
        sys.exit(2)

    device = pick_device()
    print(f"Using device: {device}")

    print(f"Loading {MODEL_ID} ...")
    processor = AutoImageProcessor.from_pretrained(MODEL_ID)
    model = SiglipForImageClassification.from_pretrained(MODEL_ID).to(device)
    model.eval()

    verdict, confidence = detect(sys.argv[1], processor, model, device)
    print(f"Verdict: {verdict}")
    print(f"Confidence: {confidence * 100:.1f}%")


if __name__ == "__main__":
    main()
