"""Public detector façade.

The rest of the project (MCP server, bot, tests) imports `detect` from here.
Two things happen at *import time*:

  1. `get_detector()` resolves `DETECTOR_MODEL` (defaults to "siglip") and
     instantiates the backend. An unknown value raises `ValueError`
     immediately — Phase 2 acceptance bar.
  2. The backend's `__init__` loads model weights. The Telegram bot needs
     the model ready before it can serve, so paying this cost up-front is
     fine.

Concurrent callers are serialized with a `threading.Lock` so two simultaneous
photos can't double-allocate GPU memory. The plan calls this an "asyncio
lock" (Key Decision 10) — `threading.Lock` is the correct primitive because
`detect()` is sync, runs blocking inference, and is invoked from both sync
contexts (tests) and async contexts (Phase 4 bot, typically via
`asyncio.to_thread`). A `threading.Lock` composes with both; an
`asyncio.Lock` would only work for the async caller.
"""

from __future__ import annotations

import threading

from detectors import DetectionResult, get_detector

# Eager singleton: validates DETECTOR_MODEL and loads weights at import time.
_detector = get_detector()
_lock = threading.Lock()


def detect(image_path: str) -> dict:
    """Run the configured detector and return a plain dict.

    Returns: {"verdict": str, "confidence": float, "summary": str}
    Raises:  FileNotFoundError if the path is missing.
             ValueError if the file is not a readable image.
    """
    with _lock:
        result: DetectionResult = _detector.detect(image_path)
    return {
        "verdict": result.verdict,
        "confidence": result.confidence,
        "summary": result.summary,
    }
