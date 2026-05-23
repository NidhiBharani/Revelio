"""Telegram bot — Phase 4 MVP.

Listens for photo messages, sends the image to the MCP `detect_ai_image`
tool, replies in-thread with the verdict. Polling-mode for local dev;
webhook mode is Phase 6.

Run:
    1. Make sure the MCP server is up:  python -m mcp_server.server
    2. Make sure .env has TELEGRAM_BOT_TOKEN set (see .env.example).
    3. python -m telegram_bot.bot

Pre-requisites (one-time, on Telegram):
    - Create a bot via @BotFather (`/newbot`), save the token to .env.
    - Add the bot to your test group.
    - Disable privacy mode for the bot:  /setprivacy → Disable
      (otherwise the bot only sees commands, not regular photo messages).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

# Logging is configured here (pulled forward from Phase 5) — the "bot keeps
# running after an error" acceptance criterion is unverifiable without it.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Quiet down httpx's per-request INFO chatter — it floods the log otherwise.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("telegram_bot")

# User-facing reply strings (Phase 4 error matrix).
REPLY_GENERIC_ERROR = "⚠️ Could not analyse this image."
REPLY_UNSUPPORTED_FORMAT = "⚠️ Unsupported image format."


def route_mcp_error(error_msg: str) -> str:
    """Pick the user-facing reply for an MCP error envelope.

    Pure function — easy to unit-test without Telegram or the MCP server.

    The Phase 3 server tags every error envelope with the originating
    exception type (e.g. ``"UnidentifiedImageError: cannot identify ..."``)
    so this routing is a substring check rather than fragile parsing.
    """
    if "UnidentifiedImageError" in error_msg:
        return REPLY_UNSUPPORTED_FORMAT
    return REPLY_GENERIC_ERROR


def _unwrap_call_result(call_result) -> dict:
    """FastMCP returns CallToolResult; pull the JSON dict out of it."""
    structured = getattr(call_result, "structuredContent", None)
    if structured:
        return structured
    return json.loads(call_result.content[0].text)


async def call_mcp_detect(mcp_url: str, image_path: str) -> dict:
    """Open an MCP client, call detect_ai_image, return the result dict.

    One session per call. Simpler than a long-lived session; the
    group-chat volume this bot targets does not need connection reuse.
    """
    async with streamable_http_client(mcp_url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.call_tool(
                "detect_ai_image", {"image_path": image_path}
            )
            return _unwrap_call_result(response)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a single photo message: download → detect → reply.

    Error matrix (matches phases-telegram-ai-image-detector.md § Phase 4):
      - Image download fails        → silent, log only
      - MCP server unreachable      → silent, log only (no group spam)
      - MCP returns error envelope  → reply with routed user message
      - Success                     → reply with result["summary"]

    Temp file cleanup is in `finally` (pulled forward from Phase 5) so a
    crash mid-inference does not leave files in /tmp.
    """
    message = update.message
    if not message or not message.photo:
        return

    mcp_url: str = context.bot_data["mcp_url"]
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None
    log.info("photo received chat=%s user=%s", chat_id, user_id)

    # Create the temp file path up-front so `finally` can always unlink it.
    fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)

    try:
        # ----- download -----
        try:
            largest = message.photo[-1]
            tg_file = await largest.get_file()
            await tg_file.download_to_drive(tmp_path)
        except Exception:
            # "Image download fails → silent fail, log only" per the matrix.
            log.exception("photo download failed chat=%s user=%s", chat_id, user_id)
            return

        # ----- detect -----
        try:
            result = await call_mcp_detect(mcp_url, tmp_path)
        except Exception:
            # "MCP server unreachable → log only, no reply" per the matrix.
            # Avoids spamming the group when the server is down.
            log.exception(
                "MCP call failed (server unreachable?) chat=%s url=%s",
                chat_id,
                mcp_url,
            )
            return

        # ----- reply -----
        if result.get("error"):
            reply = route_mcp_error(result["error"])
            log.warning(
                "detection error chat=%s reply=%r mcp_error=%s",
                chat_id,
                reply,
                result["error"],
            )
            await message.reply_text(reply, reply_to_message_id=message.message_id)
            return

        verdict = result.get("verdict")
        confidence = result.get("confidence", 0.0)
        log.info(
            "verdict chat=%s user=%s verdict=%s confidence=%.3f",
            chat_id,
            user_id,
            verdict,
            confidence,
        )
        await message.reply_text(
            result["summary"], reply_to_message_id=message.message_id
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            log.debug("temp file already gone: %s", tmp_path)


def main() -> int:
    # .env loads from CWD; explicit path keeps `python -m telegram_bot.bot`
    # working regardless of where it was launched from.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    mcp_url = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8765/mcp")

    if not token:
        print(
            "ERROR: TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env "
            "and fill in your BotFather token.",
            file=sys.stderr,
        )
        return 1

    app = Application.builder().token(token).build()
    # Stash config on bot_data so handlers can read it without globals.
    app.bot_data["mcp_url"] = mcp_url
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    log.info("Bot starting (polling mode). MCP at %s", mcp_url)
    # run_polling blocks until SIGINT/SIGTERM.
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
