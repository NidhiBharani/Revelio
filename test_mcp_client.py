"""Test client for the Phase 3 MCP server.

Round-trips a couple of images through the running MCP server and prints
the results. Also exercises the error envelope so the Phase 4 bot's
exception-routing assumptions are verified end-to-end.

Pre-req: the server must already be running in another terminal:
    python -m mcp_server.server

Run:    python test_mcp_client.py
Exit:   0 on success, 1 on any failure.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SERVER_URL = "http://127.0.0.1:8765/mcp"
REPO_ROOT = Path(__file__).resolve().parent
# Sentinel marker objects for the error-path test cases. The harness asserts
# the error envelope's `error` field starts with the named exception type.
_MISSING = object()
_UNSUPPORTED = object()

TEST_CASES = [
    # (label, image_path, expected)
    #   expected is a verdict string, _MISSING, or _UNSUPPORTED
    ("AI image", REPO_ROOT / "test_images" / "ai" / "0.jpg", "AI-Generated"),
    ("Real image", REPO_ROOT / "test_images" / "real" / "0.jpg", "Human"),
    ("Missing file", REPO_ROOT / "definitely_missing.jpg", _MISSING),
    ("Non-image file (this script)", Path(__file__), _UNSUPPORTED),
]


def _unwrap(call_result) -> dict:
    """FastMCP returns CallToolResult; pull the JSON dict out of content[0]."""
    # Newer SDK versions expose structured_content; older ones only stringified JSON.
    if getattr(call_result, "structuredContent", None):
        return call_result.structuredContent
    text = call_result.content[0].text
    return json.loads(text)


async def run() -> int:
    print(f"Connecting to {SERVER_URL} ...")
    failures = 0

    async with streamablehttp_client(SERVER_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"Tools available: {tool_names}")
            if "detect_ai_image" not in tool_names:
                print("ERROR: detect_ai_image not registered on server", file=sys.stderr)
                return 1

            for label, path, expected in TEST_CASES:
                print(f"\n--- {label}: {path}")
                response = await session.call_tool(
                    "detect_ai_image", {"image_path": str(path)}
                )
                result = _unwrap(response)
                print(json.dumps(result, indent=2))

                if expected in (_MISSING, _UNSUPPORTED):
                    expected_type = (
                        "FileNotFoundError" if expected is _MISSING else "UnidentifiedImageError"
                    )
                    if not result.get("error"):
                        print("  FAIL: expected error envelope, got success", file=sys.stderr)
                        failures += 1
                    elif expected_type not in result["error"]:
                        print(
                            f"  FAIL: expected {expected_type!r} in error, "
                            f"got {result['error']!r}",
                            file=sys.stderr,
                        )
                        failures += 1
                    else:
                        print(f"  OK (error correctly typed as {expected_type})")
                else:
                    if result.get("verdict") != expected:
                        print(
                            f"  FAIL: expected verdict={expected!r}, "
                            f"got {result.get('verdict')!r}",
                            file=sys.stderr,
                        )
                        failures += 1
                    else:
                        print(f"  OK ({result['confidence'] * 100:.1f}% confidence)")

    print()
    if failures:
        print(f"FAILED: {failures} test case(s) did not match expectations")
        return 1
    print("All round-trip cases passed.")
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except (ConnectionError, OSError) as e:
        print(
            f"\nERROR: could not reach {SERVER_URL} ({e}).\n"
            f"Start the server first:  python -m mcp_server.server",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
