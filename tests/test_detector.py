"""Unit tests for the public detector façade.

Covers the gaps the verify harness doesn't:
  - error-path contracts (missing file, unreadable file)
  - dict-shape contract (keys, types, summary format)
  - concurrency contract (the threading.Lock actually serializes calls)
  - registry validation (unknown DETECTOR_MODEL fails at startup)

Run: `python -m pytest tests/ -v`

Note: importing `detector` triggers eager model load (~5s on first run from
HF cache). This happens once per pytest session. The concurrency test
monkeypatches the singleton with a fake to avoid running real inference
in a tight loop.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import detector
from detectors.base import DetectionResult

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_AI = REPO_ROOT / "test_images" / "ai" / "0.jpg"


# ---------- Error paths ----------


def test_missing_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        detector.detect("/tmp/definitely_does_not_exist_12345.jpg")


def test_non_image_file_raises_valueerror(tmp_path: Path):
    bogus = tmp_path / "not_an_image.txt"
    bogus.write_text("this is plain text, not an image")
    with pytest.raises(ValueError):
        detector.detect(str(bogus))


# ---------- Dict-shape contract ----------


def test_returns_expected_dict_shape():
    if not SAMPLE_AI.exists():
        pytest.skip("test_images/ai/0.jpg missing; run download_test_images.py")
    result = detector.detect(str(SAMPLE_AI))

    # Keys
    assert set(result.keys()) == {"verdict", "confidence", "summary"}

    # Types and ranges
    assert isinstance(result["verdict"], str)
    assert result["verdict"] in {"AI-Generated", "Human"}
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["summary"], str)

    # Summary format is what Phase 4 posts verbatim — pin it.
    summary = result["summary"]
    assert summary.startswith("🔍 AI Image Check\n")
    assert f"Verdict: {result['verdict']}" in summary
    assert "Confidence: " in summary
    assert summary.rstrip().endswith("%")


# ---------- Concurrency contract ----------


class _SlowFakeDetector:
    """Stand-in detector that sleeps inside detect() and records overlap.

    If detector.py's lock actually serializes calls, max_concurrent stays 1.
    Without the lock, multiple threads would observe in_flight > 1.
    """

    def __init__(self, sleep_s: float = 0.05) -> None:
        self.sleep_s = sleep_s
        self.in_flight = 0
        self.max_concurrent = 0
        self.calls = 0
        self._counter_lock = threading.Lock()

    def detect(self, image_path: str) -> DetectionResult:
        with self._counter_lock:
            self.in_flight += 1
            self.calls += 1
            self.max_concurrent = max(self.max_concurrent, self.in_flight)
        time.sleep(self.sleep_s)
        with self._counter_lock:
            self.in_flight -= 1
        return DetectionResult(verdict="Human", confidence=1.0, summary="stub")


def test_concurrent_calls_are_serialized(monkeypatch):
    fake = _SlowFakeDetector(sleep_s=0.05)
    monkeypatch.setattr(detector, "_detector", fake)

    n_threads = 5
    errors: list[BaseException] = []

    def worker():
        try:
            detector.detect("ignored-by-fake")
        except BaseException as e:  # noqa: BLE001 - record and re-raise in main thread
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"worker threads raised: {errors}"
    assert fake.calls == n_threads, f"expected {n_threads} calls, got {fake.calls}"
    assert fake.max_concurrent == 1, (
        f"detector.detect() allowed {fake.max_concurrent} concurrent "
        "inferences — the threading.Lock is not serializing calls"
    )


# ---------- Registry / startup validation ----------


def test_unknown_detector_model_raises_at_import_time():
    """`import detector` with a bogus DETECTOR_MODEL must fail at startup.

    Runs in a subprocess so this test's already-imported `detector` module
    isn't reused (sys.modules cache would otherwise hide the failure).
    """
    proc = subprocess.run(
        [sys.executable, "-c", "import detector"],
        env={"DETECTOR_MODEL": "definitely_not_a_real_backend", "PATH": ""},
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode != 0, "expected import to fail, but it succeeded"
    assert "ValueError" in proc.stderr
    assert "definitely_not_a_real_backend" in proc.stderr
