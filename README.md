# Revelio

A Telegram bot that detects AI-generated images posted in group chats and replies with a verdict and confidence score. Built on the [`Ateeqq/ai-vs-human-image-detector`](https://huggingface.co/Ateeqq/ai-vs-human-image-detector) SigLIP model, served through an MCP server so the detector backend can be swapped without touching the bot.

## Status

**Phase 4 of 6 complete** — the end-to-end MVP is built. Code-level acceptance (error matrix, temp-file cleanup, logging) is verified by automated tests; live in-group testing requires a BotFather token and a test group (see [Running the Telegram bot](#running-the-telegram-bot-phase-4)). The hardening pass and webhook mode are not done yet. See [Roadmap](#roadmap).

| Phase | What | Status |
|---|---|---|
| 1 | Local model inference (CLI) | Done |
| 2 | Detector module (swappable backend) | Done |
| 3 | MCP server (HTTP transport) | Done |
| 4 | Telegram bot (polling) — first end-to-end MVP | Done (code), live test pending |
| 5 | Hardening + README polish | Not started |
| 6 | Webhook mode (deferred until deployed) | Not started |

## How it works

```
Telegram group  ─►  bot.py (polling)  ─►  MCP HTTP client
                                              │
                                              ▼
                                      mcp_server/server.py
                                              │
                                              ▼
                                       detector.py (façade)
                                              │
                                              ▼
                                  detectors/siglip.py  ──►  Ateeqq SigLIP model
```

- The bot watches a group for photo messages and downloads the highest-resolution version.
- It calls the MCP server's `detect_ai_image` tool with the local temp file path.
- The MCP server delegates to `detector.py`, which holds a singleton detector loaded from the `detectors/` registry.
- The verdict (`AI-Generated` / `Human`) plus confidence is returned and posted as a threaded reply to the original image.

The MCP server is bound to `127.0.0.1` only — the tool takes local file paths, which would be an arbitrary-file-read primitive if exposed to the network.

## Requirements

- macOS (Apple Silicon recommended — uses MPS for ~1–3s inference vs. 15–25s on CPU), Linux, or Windows
- Python 3.12 (3.13/3.14 may not have stable torch wheels yet)
- ~3 GB of disk for model weights + dependencies
- A Telegram bot token (only needed from Phase 4 onward)

## Quick start (Phase 1: local inference)

This is the only flow that works right now. It runs the detector against a single local image from the command line.

```bash
# 1. Create a Python 3.12 venv
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download the labeled verification set (3 AI + 3 real images)
python download_test_images.py

# 4. Run the detector against an image
python test_detector.py test_images/ai/0.jpg
# Verdict: AI-Generated
# Confidence: 99.9%

python test_detector.py test_images/real/0.jpg
# Verdict: Human
# Confidence: 100.0%

# 5. (Optional) Run the full verification battery against all 6 images
python verify_detector.py
# Score: 6/6 (threshold: 5/6) — OK
```

The first run downloads the SigLIP model weights (~400 MB) to `~/.cache/huggingface/`. Subsequent runs load from cache.

### Verification harness

`verify_detector.py` runs the detector against every image in `test_images/{ai,real}/` and asserts at least 5 of 6 are correctly classified (the Phase 1 acceptance bar). Exits non-zero on failure with a per-image table. Run it after any change that could affect inference (model swap, label-mapping edits, processor/transform changes).

### Unit tests

```bash
python -m pytest tests/ -v
```

Covers the parts the verification harness doesn't:

- **Error paths.** `detect("/does/not/exist.jpg")` raises `FileNotFoundError`; `detect("not_an_image.txt")` raises `ValueError`.
- **Dict shape.** Return value has exactly `{verdict, confidence, summary}`; verdict ∈ {`AI-Generated`, `Human`}; confidence is a float in [0, 1]; summary matches the format the Phase 4 bot will post verbatim.
- **Concurrency.** Five threads firing `detect()` simultaneously observe `max_concurrent == 1` — proves the `threading.Lock` in `detector.py` actually serializes calls (uses a monkeypatched slow stub to make the overlap window observable).
- **Registry.** `DETECTOR_MODEL=bogus python -c "import detector"` exits non-zero with a `ValueError` mentioning the bad name — run as a subprocess so `sys.modules` caching doesn't hide the failure.

Five tests, ~8 seconds (first run loads the SigLIP model once, then cached for the session).

## Running the MCP server (Phase 3)

The detector is also exposed as a callable MCP tool over HTTP. Two terminals:

```bash
# Terminal A — start the server
python -m mcp_server.server
# 2026-05-23 16:37:21 INFO mcp_server: Starting MCP server on http://127.0.0.1:8765/mcp
# [SiglipDetector] Loading Ateeqq/ai-vs-human-image-detector on mps ...

# Terminal B — round-trip a few images through the live server
python test_mcp_client.py
# Tools available: ['detect_ai_image']
# --- AI image: ...    OK (99.9% confidence)
# --- Real image: ...  OK (100.0% confidence)
# --- Missing file: ...    OK (error correctly typed as FileNotFoundError)
# --- Non-image file: ...  OK (error correctly typed as UnidentifiedImageError)
# All round-trip cases passed.
```

The server uses MCP's streamable HTTP transport, mounted at `/mcp` on `127.0.0.1:8765`. **Loopback-only by design** — the `detect_ai_image` tool takes a local file path, so binding to anything but `127.0.0.1` would turn it into an arbitrary-file-read primitive. If the server ever needs to move off-host, switch the tool to accept image bytes.

### Error envelope

The MCP tool always returns a JSON-serialisable dict. On success it forwards the detector's `{verdict, confidence, summary}`. On failure it returns an error envelope tagged with the originating exception type so the Phase 4 bot can route to the right user-facing reply:

```json
{ "error": "FileNotFoundError: No such image: ...", "verdict": null, "confidence": null }
{ "error": "UnidentifiedImageError: cannot identify image file ...", "verdict": null, "confidence": null }
```

The server never crashes on bad input — any unexpected exception is caught, logged with traceback, and returned as `{type_name}: {message}` so the bot stays alive.

## Running the Telegram bot (Phase 4)

End-to-end the MVP needs three things up at the same time: the MCP server, the bot, and a real Telegram chat.

> For a fully detailed walkthrough (with verification steps at each stage and a troubleshooting table), see **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)**. The summary below assumes you already know your way around BotFather.

### One-time setup

1. **Create the bot.** DM [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts, save the token.
2. **Disable privacy mode.** Still in BotFather: `/setprivacy` → pick your bot → **Disable**. Without this, the bot only sees messages that start with `/` and will never see group photos.
3. **Add the bot to your test group** as a regular member.
4. **Configure `.env`.** Copy `.env.example` to `.env` and paste the token:
   ```bash
   cp .env.example .env
   # edit .env, replace your_token_here
   ```

### Run

Three terminals:

```bash
# Terminal A — MCP server
python -m mcp_server.server

# Terminal B — Telegram bot
python -m telegram_bot.bot
# 2026-05-23 16:42:01 INFO telegram_bot: Bot starting (polling mode). MCP at http://127.0.0.1:8765/mcp

# Terminal C — your Telegram client (phone or desktop)
# Post a photo in the test group. Within a few seconds the bot replies
# as a threaded reply to the original photo message:
#   🔍 AI Image Check
#   Verdict: AI-Generated
#   Confidence: 99.9%
```

### Error matrix

What the bot does when things go wrong (also encoded in `tests/test_bot.py`):

| Situation | Detection | User-facing reply |
|---|---|---|
| Success | MCP returns `verdict` + `summary` | Replies in thread with the summary |
| Unsupported format | MCP `error` contains `UnidentifiedImageError` | `⚠️ Unsupported image format.` |
| Generic inference failure | MCP `error` is anything else | `⚠️ Could not analyse this image.` |
| MCP server unreachable | `call_mcp_detect` raises | **Silent** (log only — avoids spamming the group when the server is down) |
| Photo download failed | Telegram API exception before MCP call | **Silent** (log only) |
| Non-photo message | `filters.PHOTO` filters it out | Ignored |

Temp files in `/tmp/tmp*.jpg` are unlinked in `finally` — verified by `test_handle_photo_cleans_up_temp_file`, which forces an MCP failure mid-call and asserts the file is gone.

### What's automated vs. manual

Tests in `tests/test_bot.py` cover:
- Error-matrix routing (`route_mcp_error` with 5 parametrised inputs)
- MCP wrapper against the live server (skipped if server is down)
- `handle_photo` end-to-end with a mocked Telegram update and mocked MCP — success, both error branches, MCP-down, download-fail, non-photo, temp-file cleanup

Not automated (requires real Telegram):
- The 5-second SLA from "post photo → bot reply"
- Privacy-mode-disabled side of BotFather config
- Multiple group members posting photos
- 30-min uptime soak (deferred to Phase 5)

### Device selection

`test_detector.py` automatically picks the best available device in this order:

1. **MPS** (Apple Silicon Metal Performance Shaders)
2. **CUDA** (Nvidia GPU)
3. **CPU**

On a Mac with unified memory you should see `Using device: mps` and inference completes in ~1–3 seconds.

## Project layout

```
fake_detector/
├── README.md                              # this file
├── phases-telegram-ai-image-detector.md   # PRD: phase-by-phase build plan
├── implementation-plan.md                 # concrete decisions + per-phase steps
├── requirements.txt                       # Python dependencies (minor-version pinned)
├── detectors/                             # Phase 2 — swappable detector backends
│   ├── __init__.py                        #   re-exports get_detector, BaseDetector, DetectionResult
│   ├── base.py                            #   ABC + DetectionResult dataclass
│   ├── siglip.py                          #   current backend (Ateeqq SigLIP)
│   └── registry.py                        #   name → class map, reads DETECTOR_MODEL
├── detector.py                            # Phase 2 — public façade: eager singleton, lock-guarded
├── mcp_server/                            # Phase 3 — MCP HTTP server
│   ├── __init__.py
│   └── server.py                          #   FastMCP, streamable-http, /mcp on 127.0.0.1:8765
├── telegram_bot/                          # Phase 4 — Telegram bot
│   ├── __init__.py
│   └── bot.py                             #   polling, MCP client, error matrix, temp-file cleanup
├── .env.example                           # Phase 4 — copy to .env and fill in your bot token
├── download_test_images.py                # fetches 3 AI + 3 real test images
├── test_detector.py                       # Phase 1 CLI: runs the configured detector on one image
├── verify_detector.py                     # Phase 1/2 harness: asserts ≥5/6 correct
├── test_mcp_client.py                     # Phase 3 — round-trips images through the running server
├── tests/                                 # pytest suite
│   ├── test_detector.py                   #   Phase 2 — error paths, dict shape, concurrency, registry
│   └── test_bot.py                        #   Phase 4 — error matrix, MCP client wrapper, temp-file lifecycle
└── test_images/
    ├── ai/                                # AI-generated verification images
    └── real/                              # real-photo verification images
```

Items planned for later phases (not yet present):

```
requirements.lock  # Phase 5 — pinned via `pip freeze`
```

### Using the detector from your own code

`detector.py` is the stable public entry point:

```python
from detector import detect

result = detect("path/to/image.jpg")
# {"verdict": "AI-Generated", "confidence": 0.999, "summary": "..."}
```

Importing `detector` eagerly resolves `DETECTOR_MODEL` (default `"siglip"`)
and loads the model. An unknown value raises `ValueError` immediately —
misconfiguration surfaces at startup, not on the first inference call.
Concurrent callers are serialized with a `threading.Lock` so two
simultaneous photos can't double-allocate GPU memory.

### Swapping the detector backend

1. Drop a new module into `detectors/` whose class subclasses `BaseDetector`.
2. Register it in `detectors/registry.py`: `_REGISTRY["myname"] = MyDetector`.
3. Set `DETECTOR_MODEL=myname` in your environment.

No other code changes.

## Verification dataset

The detector is sanity-checked against 6 images fetched from HuggingFace:

- **AI images** (3): `AiArtData` class from [`Hemg/AI-Generated-vs-Real-Images-Datasets`](https://huggingface.co/datasets/Hemg/AI-Generated-vs-Real-Images-Datasets).
- **Real photos** (3): [`nielsr/CelebA-faces`](https://huggingface.co/datasets/nielsr/CelebA-faces).

Two datasets are used because the Hemg dataset's "RealArt" class is hand-painted artwork, and the Ateeqq model — trained on AI-vs-real *photographs* — correctly flags paintings as AI. CelebA gives us real-domain photos for the human class. See [implementation-plan.md](implementation-plan.md) Key Decision 3 for the full rationale.

## Configuration (Phase 4+)

These environment variables are not yet read by any code. They define the contract for the upcoming bot and MCP server:

```dotenv
TELEGRAM_BOT_TOKEN=your_token_here
MCP_SERVER_URL=http://127.0.0.1:8765/mcp
DETECTOR_MODEL=siglip
```

- `TELEGRAM_BOT_TOKEN` — issued by [@BotFather](https://t.me/BotFather). Phase 4 prerequisite.
- `MCP_SERVER_URL` — full URL including the `/mcp` path. The bot will refuse to start if this is unreachable.
- `DETECTOR_MODEL` — registry key for the detector backend; only `siglip` is implemented for now.

### Telegram bot setup (Phase 4 prerequisite)

1. Start a chat with [@BotFather](https://t.me/BotFather) and send `/newbot`. Save the bot token.
2. Send `/setprivacy`, select your bot, and choose **Disabled** — required so the bot can see all group messages, not just commands.
3. Add the bot to your test group.

## Architecture decisions

For the rationale behind the technical choices (MPS device selection, MCP HTTP vs. stdio transport, eager singleton validation, single-flight detection, etc.), see [implementation-plan.md](implementation-plan.md). The phased build plan lives in [phases-telegram-ai-image-detector.md](phases-telegram-ai-image-detector.md).

Highlights:

- **MCP transport: HTTP, not stdio.** Decouples the bot from the server process and makes the Phase 5 startup health check meaningful.
- **Detector behind a registry.** Swapping to a different model later is one file plus an env var change.
- **`127.0.0.1`-only bind.** Tool accepts local file paths; never expose to the network.
- **Concurrency.** Single-flight `asyncio.Lock` around model inference so concurrent photos queue instead of double-allocating GPU memory.

## Roadmap

Each phase is independently completable and testable. Acceptance criteria for each are spelled out in [phases-telegram-ai-image-detector.md](phases-telegram-ai-image-detector.md).

- [x] **Phase 1** — Local CLI inference, 6/6 on verification battery
- [x] **Phase 2** — `detectors/` package + `detector.py` façade with eager-validated singleton
- [x] **Phase 3** — MCP server (streamable HTTP, loopback-only) exposing `detect_ai_image`
- [x] **Phase 4** — Telegram bot (polling): error matrix, temp-file cleanup, logging — 14 automated tests pass; live in-group test pending BotFather setup
- [ ] **Phase 3** — MCP server exposing `detect_ai_image` over HTTP
- [ ] **Phase 4** — Telegram bot (polling), first end-to-end working version
- [ ] **Phase 5** — Health checks, timeouts, structured logging, requirements lock file
- [ ] **Phase 6** — Webhook mode (deferred until deployed to a VPS with HTTPS)

## Contributing

This is currently a personal project; the design docs ([PRD](phases-telegram-ai-image-detector.md), [implementation plan](implementation-plan.md)) are the source of truth for what's intended. PRs and issues welcome once Phase 4 lands and the project is actually useful end-to-end.

If you want to swap in a different detection model, the path is now in place: add a single file (`detectors/yourmodel.py`) plus a registry entry — see [Swapping the detector backend](#swapping-the-detector-backend).

## License

AGPL-3.0. See [LICENSE](LICENSE). Because this is intended to run as a network-accessible bot, AGPL is the right copyleft — anyone running a modified version as a service must offer the modified source to users interacting with it over the network.

## Credits

- Detection model: [`Ateeqq/ai-vs-human-image-detector`](https://huggingface.co/Ateeqq/ai-vs-human-image-detector) — SigLIP fine-tuned for AI vs. human image classification.
- Verification datasets: [`Hemg/AI-Generated-vs-Real-Images-Datasets`](https://huggingface.co/datasets/Hemg/AI-Generated-vs-Real-Images-Datasets), [`nielsr/CelebA-faces`](https://huggingface.co/datasets/nielsr/CelebA-faces).
- Built with [`transformers`](https://github.com/huggingface/transformers), [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot), and the [Model Context Protocol](https://modelcontextprotocol.io/) Python SDK.
