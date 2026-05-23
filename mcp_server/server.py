"""MCP server exposing the detector as a callable tool.

Run:  `python -m mcp_server.server`

Transport: streamable HTTP, mounted at /mcp on 127.0.0.1:8765. Loopback-only
bind is deliberate — the `detect_ai_image` tool takes a local file path. If
this were exposed beyond localhost it would be an arbitrary-file-read
primitive. If the server ever needs to move off-host, switch the tool to
accept image bytes instead of a path.

The server is process-independent: the Phase 4 Telegram bot connects as a
client. Killing the client never kills the server.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

import detector  # eager singleton — model loads here, before run()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("mcp_server")

HOST = "127.0.0.1"
PORT = 8765

mcp = FastMCP(
    "fake-detector",
    host=HOST,
    port=PORT,
    # streamable_http_path defaults to "/mcp" — leave it explicit for clarity.
    streamable_http_path="/mcp",
    instructions=(
        "Detect whether an image is AI-generated or a real photograph. "
        "Call detect_ai_image(image_path) with a path to a local image file."
    ),
)


def _error_response(exc: BaseException) -> dict[str, Any]:
    """Convert an exception into the tool's structured error envelope.

    The Phase 4 bot string-matches on the error message to choose a
    user-facing reply (see phases doc § Phase 4 error matrix). We surface
    the underlying exception type — including chained __cause__ — so the
    bot can distinguish "file not found" from "unsupported image format"
    from "everything else."
    """
    cause = exc.__cause__
    type_name = type(cause).__name__ if cause is not None else type(exc).__name__
    return {
        "error": f"{type_name}: {exc}",
        "verdict": None,
        "confidence": None,
    }


@mcp.tool()
def detect_ai_image(image_path: str) -> dict[str, Any]:
    """Classify a local image as AI-generated or a real photograph.

    Args:
        image_path: Absolute or relative path to an image file readable by PIL.

    Returns:
        Success: {"verdict": str, "confidence": float, "summary": str}
        Failure: {"error": str, "verdict": None, "confidence": None}
                 The `error` field starts with the originating exception type
                 (e.g. "FileNotFoundError: ...", "UnidentifiedImageError: ...")
                 so callers can route on it.
    """
    start = time.perf_counter()
    try:
        result = detector.detect(image_path)
    except FileNotFoundError as e:
        latency_ms = (time.perf_counter() - start) * 1000
        log.warning("detect_ai_image path=%s FileNotFoundError (%.1f ms)", image_path, latency_ms)
        return {"error": f"FileNotFoundError: {e}", "verdict": None, "confidence": None}
    except ValueError as e:
        latency_ms = (time.perf_counter() - start) * 1000
        log.warning("detect_ai_image path=%s ValueError (%.1f ms): %s", image_path, latency_ms, e)
        return _error_response(e)
    except Exception as e:  # noqa: BLE001 — last-resort guard so the server never crashes
        latency_ms = (time.perf_counter() - start) * 1000
        log.exception("detect_ai_image path=%s unexpected error (%.1f ms)", image_path, latency_ms)
        return {"error": f"{type(e).__name__}: {e}", "verdict": None, "confidence": None}

    latency_ms = (time.perf_counter() - start) * 1000
    log.info(
        "detect_ai_image path=%s verdict=%s confidence=%.3f (%.1f ms)",
        image_path,
        result["verdict"],
        result["confidence"],
        latency_ms,
    )
    return result


def main() -> None:
    log.info("Starting MCP server on http://%s:%d/mcp", HOST, PORT)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
