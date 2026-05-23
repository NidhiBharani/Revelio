"""SigLIP-based detector wrapping `Ateeqq/ai-vs-human-image-detector`.

Loads the model and processor once in `__init__`. Picks the best available
device (MPS → CUDA → CPU). Maps raw model labels to display strings
internally, so the rest of the codebase stays detector-agnostic.
"""

from __future__ import annotations

from pathlib import Path

import torch
from PIL import Image, UnidentifiedImageError
from transformers import AutoImageProcessor, SiglipForImageClassification

from .base import BaseDetector, DetectionResult

MODEL_ID = "Ateeqq/ai-vs-human-image-detector"

# Raw label codes returned by `model.config.id2label` → user-facing strings.
# If the upstream model is retrained with different label codes, the assertion
# in `__init__` will fail loudly rather than silently misclassify.
_DISPLAY = {"ai": "AI-Generated", "hum": "Human", "human": "Human"}


def pick_device() -> torch.device:
    """Pick the fastest locally-available torch device.

    Apple Silicon → MPS; Nvidia → CUDA; else CPU. Switching hosts (e.g. moving
    to a GPU box) requires no code change — the model is `.to(device)` on load.
    """
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class SiglipDetector(BaseDetector):
    def __init__(self) -> None:
        self.device = pick_device()
        # Print-on-load: lets tests verify the model is constructed exactly once.
        print(f"[SiglipDetector] Loading {MODEL_ID} on {self.device} ...")
        self.processor = AutoImageProcessor.from_pretrained(MODEL_ID)
        self.model = SiglipForImageClassification.from_pretrained(MODEL_ID).to(self.device)
        self.model.eval()

        # Safety net: fail loudly if the model is retrained with new label codes.
        for raw in self.model.config.id2label.values():
            key = raw.strip().lower()
            if key not in _DISPLAY:
                raise RuntimeError(
                    f"{MODEL_ID} returned unknown label code {raw!r}; "
                    f"update _DISPLAY in detectors/siglip.py "
                    f"(known: {sorted(_DISPLAY)})"
                )

    def detect(self, image_path: str) -> DetectionResult:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"No such image: {image_path}")
        try:
            image = Image.open(path).convert("RGB")
        except UnidentifiedImageError as e:
            raise ValueError(f"Could not open {image_path} as an image: {e}") from e
        except OSError as e:
            raise ValueError(f"Could not open {image_path} as an image: {e}") from e

        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            logits = self.model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)[0]
        top_idx = int(torch.argmax(probs).item())
        confidence = float(probs[top_idx].item())
        raw_label = self.model.config.id2label[top_idx]
        verdict = _DISPLAY[raw_label.strip().lower()]
        summary = (
            "🔍 AI Image Check\n"
            f"Verdict: {verdict}\n"
            f"Confidence: {confidence * 100:.1f}%"
        )
        return DetectionResult(verdict=verdict, confidence=confidence, summary=summary)
