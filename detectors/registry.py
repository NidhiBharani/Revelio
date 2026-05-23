"""Name → detector class registry.

`DETECTOR_MODEL` (env var) selects the backend. To add a new detector:

    1. Implement it as a subclass of `BaseDetector` in a new module here.
    2. Register the class below.
    3. Set `DETECTOR_MODEL=<name>` in `.env`.
"""

from __future__ import annotations

import os

from .base import BaseDetector
from .siglip import SiglipDetector

_REGISTRY: dict[str, type[BaseDetector]] = {
    "siglip": SiglipDetector,
}

_DEFAULT = "siglip"


def get_detector(name: str | None = None) -> BaseDetector:
    """Instantiate the detector selected by `name` (or `DETECTOR_MODEL`).

    Raises `ValueError` if the name is not registered. The error is
    deliberately raised eagerly so misconfiguration surfaces at startup,
    not on the first inference call.
    """
    chosen = name or os.environ.get("DETECTOR_MODEL", _DEFAULT)
    if chosen not in _REGISTRY:
        raise ValueError(
            f"Unknown DETECTOR_MODEL={chosen!r}; "
            f"registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[chosen]()
