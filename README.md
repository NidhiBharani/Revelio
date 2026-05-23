# fake_detector

A Telegram bot that detects AI-generated images posted in group chats and replies with a verdict and confidence score. Built on the [`Ateeqq/ai-vs-human-image-detector`](https://huggingface.co/Ateeqq/ai-vs-human-image-detector) SigLIP model, served through an MCP server so the detector backend can be swapped without touching the bot.

## Status

**Phase 1 of 6 complete** — local model inference is working. The Telegram bot, MCP server, and hardening phases are not implemented yet. See [Roadmap](#roadmap).

| Phase | What | Status |
|---|---|---|
| 1 | Local model inference (CLI) | Done |
| 2 | Detector module (swappable backend) | Not started |
| 3 | MCP server (HTTP transport) | Not started |
| 4 | Telegram bot (polling) — first end-to-end MVP | Not started |
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
```

The first run downloads the SigLIP model weights (~400 MB) to `~/.cache/huggingface/`. Subsequent runs load from cache.

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
├── download_test_images.py                # fetches 3 AI + 3 real test images
├── test_detector.py                       # Phase 1 CLI: runs SigLIP on one image
└── test_images/
    ├── ai/                                # AI-generated verification images
    └── real/                              # real-photo verification images
```

Items planned for later phases (not yet present):

```
detectors/        # Phase 2 — swappable backend (base.py, siglip.py, registry.py)
detector.py       # Phase 2 — public façade
mcp_server/       # Phase 3 — MCP HTTP server exposing detect_ai_image
telegram_bot/     # Phase 4 — python-telegram-bot polling loop
test_mcp_client.py# Phase 3 — round-trip test client
.env.example      # Phase 4 — config template
```

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
- [ ] **Phase 2** — `detectors/` package + `detector.py` façade with eager-validated singleton
- [ ] **Phase 3** — MCP server exposing `detect_ai_image` over HTTP
- [ ] **Phase 4** — Telegram bot (polling), first end-to-end working version
- [ ] **Phase 5** — Health checks, timeouts, structured logging, requirements lock file
- [ ] **Phase 6** — Webhook mode (deferred until deployed to a VPS with HTTPS)

## Contributing

This is currently a personal project; the design docs ([PRD](phases-telegram-ai-image-detector.md), [implementation plan](implementation-plan.md)) are the source of truth for what's intended. PRs and issues welcome once Phase 4 lands and the project is actually useful end-to-end.

If you want to swap in a different detection model, the right move is to wait until Phase 2 is done — then it's a single file (`detectors/yourmodel.py`) plus a registry entry.

## License

MIT. See [LICENSE](LICENSE).

## Credits

- Detection model: [`Ateeqq/ai-vs-human-image-detector`](https://huggingface.co/Ateeqq/ai-vs-human-image-detector) — SigLIP fine-tuned for AI vs. human image classification.
- Verification datasets: [`Hemg/AI-Generated-vs-Real-Images-Datasets`](https://huggingface.co/datasets/Hemg/AI-Generated-vs-Real-Images-Datasets), [`nielsr/CelebA-faces`](https://huggingface.co/datasets/nielsr/CelebA-faces).
- Built with [`transformers`](https://github.com/huggingface/transformers), [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot), and the [Model Context Protocol](https://modelcontextprotocol.io/) Python SDK.
