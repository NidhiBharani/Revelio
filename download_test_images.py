"""Download a small labeled set of AI / real images for sanity-checking the detector.

Run: `python download_test_images.py`
Saves 3 AI + 3 real images to test_images/{ai,real}/. Re-running is a no-op once populated.

Source datasets:
  - AI:   Hemg/AI-Generated-vs-Real-Images-Datasets (AiArtData split — AI-generated images)
  - Real: nielsr/CelebA-faces (real celebrity photographs)

Why two datasets: Ateeqq/ai-vs-human-image-detector is trained on photos, not paintings.
The Hemg dataset's "RealArt" class is hand-painted artwork, which the model misclassifies
as AI — not a model bug, just a domain mismatch. CelebA gives us real photos in the
domain the model was trained on.
"""

from __future__ import annotations

from pathlib import Path

from datasets import load_dataset

AI_DATASET = "Hemg/AI-Generated-vs-Real-Images-Datasets"
AI_CLASS_NAME = "AiArtData"
REAL_DATASET = "nielsr/CelebA-faces"

N_PER_CLASS = 3
ROOT = Path(__file__).parent / "test_images"
AI_DIR = ROOT / "ai"
REAL_DIR = ROOT / "real"


def _already_populated() -> bool:
    return (
        AI_DIR.is_dir()
        and REAL_DIR.is_dir()
        and len(list(AI_DIR.glob("*.jpg"))) >= N_PER_CLASS
        and len(list(REAL_DIR.glob("*.jpg"))) >= N_PER_CLASS
    )


def _save_ai() -> None:
    ds = load_dataset(AI_DATASET, split="train", streaming=True)
    names = ds.features["label"].names
    if AI_CLASS_NAME not in names:
        raise RuntimeError(
            f"{AI_DATASET} no longer has class {AI_CLASS_NAME!r}; got {names}"
        )
    ai_idx = names.index(AI_CLASS_NAME)
    saved = 0
    for row in ds:
        if saved >= N_PER_CLASS:
            break
        if row["label"] != ai_idx:
            continue
        path = AI_DIR / f"{saved}.jpg"
        row["image"].convert("RGB").save(path, "JPEG")
        print(f"  saved {path}")
        saved += 1
    if saved < N_PER_CLASS:
        raise RuntimeError(f"AI stream exhausted at {saved}/{N_PER_CLASS}")


def _save_real() -> None:
    ds = load_dataset(REAL_DATASET, split="train", streaming=True)
    saved = 0
    for row in ds:
        if saved >= N_PER_CLASS:
            break
        path = REAL_DIR / f"{saved}.jpg"
        row["image"].convert("RGB").save(path, "JPEG")
        print(f"  saved {path}")
        saved += 1
    if saved < N_PER_CLASS:
        raise RuntimeError(f"Real stream exhausted at {saved}/{N_PER_CLASS}")


def main() -> None:
    if _already_populated():
        print(f"test_images/ already has >={N_PER_CLASS} per class — skipping download.")
        return

    AI_DIR.mkdir(parents=True, exist_ok=True)
    REAL_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading AI images from {AI_DATASET} ...")
    _save_ai()
    print(f"Downloading real photos from {REAL_DATASET} ...")
    _save_real()
    print(f"Done. {N_PER_CLASS} AI + {N_PER_CLASS} real images in test_images/.")


if __name__ == "__main__":
    main()
