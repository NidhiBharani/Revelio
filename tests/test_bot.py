"""Phase 4 bot tests — the parts that don't require a real Telegram bot.

Full end-to-end testing requires a BotFather token, a test group, and
privacy mode disabled (see telegram_bot/bot.py docstring). That can only
be done manually. These tests cover:

  - `route_mcp_error` routing logic (pure function)
  - `call_mcp_detect` against the live MCP server (skipped if server is down)
  - `handle_photo` error matrix via mocked Telegram update + mocked MCP
"""

from __future__ import annotations

import asyncio
import os
import socket
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot import bot as bot_module
from telegram_bot.bot import (
    REPLY_GENERIC_ERROR,
    REPLY_UNSUPPORTED_FORMAT,
    call_mcp_detect,
    handle_photo,
    route_mcp_error,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_AI = REPO_ROOT / "test_images" / "ai" / "0.jpg"
MCP_URL = "http://127.0.0.1:8765/mcp"


def _mcp_server_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=0.2):
            return True
    except OSError:
        return False


# ---------- route_mcp_error ----------


@pytest.mark.parametrize(
    "error_msg, expected",
    [
        ("UnidentifiedImageError: cannot identify image file 'foo.txt'", REPLY_UNSUPPORTED_FORMAT),
        ("FileNotFoundError: No such image: /tmp/bar.jpg", REPLY_GENERIC_ERROR),
        ("OSError: image file is truncated", REPLY_GENERIC_ERROR),
        ("RuntimeError: something exploded", REPLY_GENERIC_ERROR),
        ("", REPLY_GENERIC_ERROR),
    ],
)
def test_route_mcp_error(error_msg, expected):
    assert route_mcp_error(error_msg) == expected


# ---------- call_mcp_detect (live MCP server required) ----------


@pytest.mark.skipif(not _mcp_server_up(), reason="MCP server not running on 127.0.0.1:8765")
def test_call_mcp_detect_against_live_server():
    if not SAMPLE_AI.exists():
        pytest.skip("test_images/ai/0.jpg missing; run download_test_images.py")
    result = asyncio.run(call_mcp_detect(MCP_URL, str(SAMPLE_AI)))
    assert result.get("verdict") == "AI-Generated"
    assert isinstance(result["confidence"], float)
    assert "summary" in result


@pytest.mark.skipif(not _mcp_server_up(), reason="MCP server not running on 127.0.0.1:8765")
def test_call_mcp_detect_error_envelope():
    """Confirm the bot still receives a structured error dict on bad input."""
    result = asyncio.run(call_mcp_detect(MCP_URL, "/no/such/file.jpg"))
    assert result.get("verdict") is None
    assert "FileNotFoundError" in result.get("error", "")


# ---------- handle_photo error matrix (mocked) ----------


def _make_mock_update(photo_present: bool = True) -> MagicMock:
    """Construct a Telegram Update double for handle_photo."""
    update = MagicMock()
    if not photo_present:
        update.message = None
        return update

    message = MagicMock()
    message.chat.id = 12345
    message.from_user.id = 67890
    message.message_id = 1
    message.reply_text = AsyncMock()

    photo_size = MagicMock()
    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock(side_effect=_make_dummy_file)
    photo_size.get_file = AsyncMock(return_value=tg_file)
    message.photo = [photo_size]

    update.message = message
    return update


async def _make_dummy_file(path):
    """Mimic Telegram's download_to_drive: write a tiny valid JPEG to `path`."""
    # 1x1 white JPEG, 125 bytes — enough for the bot's temp-file flow.
    from PIL import Image

    Image.new("RGB", (1, 1), color="white").save(path, "JPEG")


def _make_context(mcp_url: str = MCP_URL) -> MagicMock:
    ctx = MagicMock()
    ctx.bot_data = {"mcp_url": mcp_url}
    return ctx


def test_handle_photo_success_replies_with_summary(monkeypatch, tmp_path):
    """Happy path: MCP returns a verdict, bot replies with `summary`."""
    fake_result = {
        "verdict": "AI-Generated",
        "confidence": 0.987,
        "summary": "🔍 AI Image Check\nVerdict: AI-Generated\nConfidence: 98.7%",
    }

    async def fake_call(url, path):
        return fake_result

    monkeypatch.setattr(bot_module, "call_mcp_detect", fake_call)

    update = _make_mock_update()
    ctx = _make_context()
    asyncio.run(handle_photo(update, ctx))

    update.message.reply_text.assert_called_once()
    args, kwargs = update.message.reply_text.call_args
    assert args[0] == fake_result["summary"]
    assert kwargs["reply_to_message_id"] == 1


def test_handle_photo_unsupported_format_reply(monkeypatch):
    """MCP returns UnidentifiedImageError → bot replies with format message."""

    async def fake_call(url, path):
        return {
            "verdict": None,
            "confidence": None,
            "error": "UnidentifiedImageError: cannot identify image file ...",
        }

    monkeypatch.setattr(bot_module, "call_mcp_detect", fake_call)

    update = _make_mock_update()
    asyncio.run(handle_photo(update, _make_context()))

    update.message.reply_text.assert_called_once()
    assert update.message.reply_text.call_args.args[0] == REPLY_UNSUPPORTED_FORMAT


def test_handle_photo_generic_error_reply(monkeypatch):
    """MCP returns non-PIL error → bot replies with generic error message."""

    async def fake_call(url, path):
        return {
            "verdict": None,
            "confidence": None,
            "error": "RuntimeError: weights file corrupted",
        }

    monkeypatch.setattr(bot_module, "call_mcp_detect", fake_call)

    update = _make_mock_update()
    asyncio.run(handle_photo(update, _make_context()))

    update.message.reply_text.assert_called_once()
    assert update.message.reply_text.call_args.args[0] == REPLY_GENERIC_ERROR


def test_handle_photo_mcp_unreachable_is_silent(monkeypatch):
    """MCP raises → no reply (avoids spamming the group when server is down)."""

    async def fake_call(url, path):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(bot_module, "call_mcp_detect", fake_call)

    update = _make_mock_update()
    asyncio.run(handle_photo(update, _make_context()))

    update.message.reply_text.assert_not_called()


def test_handle_photo_download_failure_is_silent(monkeypatch):
    """Telegram download raises → no reply, log only."""

    async def fake_call(url, path):  # pragma: no cover - must not be reached
        raise AssertionError("call_mcp_detect should not run if download fails")

    monkeypatch.setattr(bot_module, "call_mcp_detect", fake_call)

    update = _make_mock_update()
    update.message.photo[0].get_file = AsyncMock(side_effect=RuntimeError("403 forbidden"))

    asyncio.run(handle_photo(update, _make_context()))

    update.message.reply_text.assert_not_called()


def test_handle_photo_cleans_up_temp_file(monkeypatch):
    """Temp file is always unlinked, even when MCP raises mid-call."""
    created_paths: list[str] = []

    async def fake_call(url, path):
        created_paths.append(path)
        assert os.path.exists(path), "temp file should exist while MCP is being called"
        raise RuntimeError("simulated inference failure")

    monkeypatch.setattr(bot_module, "call_mcp_detect", fake_call)

    update = _make_mock_update()
    asyncio.run(handle_photo(update, _make_context()))

    assert created_paths, "fake_call should have been invoked"
    assert not os.path.exists(created_paths[0]), (
        f"temp file {created_paths[0]} was not cleaned up after MCP failure"
    )


def test_handle_photo_ignores_non_photo_messages(monkeypatch):
    """Non-photo update → handler returns immediately, no reply, no MCP call."""
    called = False

    async def fake_call(url, path):  # pragma: no cover
        nonlocal called
        called = True

    monkeypatch.setattr(bot_module, "call_mcp_detect", fake_call)

    update = _make_mock_update(photo_present=False)
    asyncio.run(handle_photo(update, _make_context()))

    assert not called
