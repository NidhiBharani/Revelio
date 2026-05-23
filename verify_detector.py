"""Verification harness: run the configured detector against every image in
`test_images/{ai,real}/` and assert at least 5 of 6 are correctly classified.

Run: `python verify_detector.py`
Exits 0 on pass, 1 on fail. Also doubles as the Phase 2 acceptance check:
because `detector.py` is an eager singleton, the model loads exactly once
and `[SiglipDetector] Loading ...` should appear exactly once in the output.
"""

from __future__ import annotations

import sys
from pathlib import Path

from detector import detect

ROOT = Path(__file__).parent / "test_images"
EXPECTED = {
    ROOT / "ai": "AI-Generated",
    ROOT / "real": "Human",
}
PASS_THRESHOLD = 5  # out of 6


def main() -> int:
    images: list[tuple[Path, str]] = []
    for folder, expected in EXPECTED.items():
        if not folder.is_dir():
            print(f"ERROR: missing {folder}; run download_test_images.py first.", file=sys.stderr)
            return 1
        for img in sorted(folder.glob("*.jpg")):
            images.append((img, expected))

    if not images:
        print("ERROR: no test images found.", file=sys.stderr)
        return 1

    print()
    print(f"{'Image':<30}  {'Expected':<13}  {'Got':<13}  {'Conf':>6}  Result")
    print("-" * 76)

    correct = 0
    for path, expected in images:
        result = detect(str(path))
        verdict = result["verdict"]
        confidence = result["confidence"]
        ok = verdict == expected
        correct += int(ok)
        rel = path.relative_to(ROOT.parent)
        mark = "PASS" if ok else "FAIL"
        print(f"{str(rel):<30}  {expected:<13}  {verdict:<13}  {confidence * 100:5.1f}%  {mark}")

    total = len(images)
    print("-" * 76)
    print(f"Score: {correct}/{total} (threshold: {PASS_THRESHOLD}/{total})")

    if correct < PASS_THRESHOLD:
        # If the score looks inverted, suspect the label mapping.
        if correct <= total - PASS_THRESHOLD:
            print(
                "\nHint: score looks inverted — check _DISPLAY / id2label mapping "
                "in detectors/siglip.py.",
                file=sys.stderr,
            )
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
