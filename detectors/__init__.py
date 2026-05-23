"""Detector package: swappable AI-vs-human image classifiers.

Public surface:
    BaseDetector       — interface every backend implements
    DetectionResult    — return type from `detect()`
    get_detector(name) — instantiate the chosen backend
"""

from .base import BaseDetector, DetectionResult
from .registry import get_detector

__all__ = ["BaseDetector", "DetectionResult", "get_detector"]
