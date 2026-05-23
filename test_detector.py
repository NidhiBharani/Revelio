"""Single-image CLI wrapper around `detector.detect()`.

Run: `python test_detector.py path/to/image.jpg`

All model loading lives in `detectors/siglip.py` via the `detector` façade —
importing this module triggers an eager load (and validates `DETECTOR_MODEL`).
"""

from __future__ import annotations

import sys

from detector import detect


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python test_detector.py <image_path>", file=sys.stderr)
        return 2
    result = detect(sys.argv[1])
    print(f"Verdict: {result['verdict']}")
    print(f"Confidence: {result['confidence'] * 100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
