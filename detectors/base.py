"""Detector interface and shared data types.

Every backend lives in its own module under `detectors/` and subclasses
`BaseDetector`. Adding a new backend is: drop in a new module, register it in
`registry.py`, set `DETECTOR_MODEL=<name>` in `.env`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionResult:
    """Result of running a detector on a single image.

    `summary` is posted verbatim by the Telegram bot — it includes any
    user-facing formatting (emoji, line breaks). Keep it short.
    """

    verdict: str          # "AI-Generated" | "Human"  (display strings)
    confidence: float     # 0.0–1.0
    summary: str          # ready-to-post string for the bot


class BaseDetector(ABC):
    """Abstract base for all AI-vs-human image detectors.

    Implementations must:
      - Load the model in `__init__` (so the cost is paid once per process).
      - Raise `FileNotFoundError` if `image_path` does not exist.
      - Raise `ValueError` if PIL cannot open the file as an image.
      - Return display-ready labels in `DetectionResult.verdict`
        (e.g. "AI-Generated", not raw model codes like "ai").
    """

    @abstractmethod
    def detect(self, image_path: str) -> DetectionResult:
        ...
