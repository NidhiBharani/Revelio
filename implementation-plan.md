# Implementation Plan: Telegram AI Image Detection Bot

Companion to [phases-telegram-ai-image-detector.md](phases-telegram-ai-image-detector.md). This document records the concrete decisions and per-phase steps agreed during planning.

---

## Key decisions

### 1. Device selection (Mac unified memory → GPU later)
Use **MPS** (Metal Performance Shaders) on Apple Silicon instead of CPU. On unified-memory Macs, SigLIP inference drops from ~15–25s (CPU) to ~1–3s (MPS), making Phase 4's 5s SLA realistic.

Implement a `pick_device()` helper:
- `mps` if `torch.backends.mps.is_available()`
- `cuda` if `torch.cuda.is_available()`
- else `cpu`

This means moving to a discrete GPU later is a no-op for the code.

### 2. MCP transport: HTTP, not stdio
MCP has two transports:
- **stdio (SDK default):** the client *spawns* the server as a child process and talks down a pipe (walkie-talkie). One bot ↔ one server, tied together.
- **HTTP/SSE:** the server runs independently on a port. The bot connects over the network (phone call). Processes start and stop independently.

The PRD describes the HTTP model ("starts on localhost," "two terminal commands"). **Use the SDK's streamable HTTP transport** explicitly — it matches the PRD, decouples processes, and makes Phase 5's startup health check meaningful.

### 3. Test images for label verification
Pull a labeled set from HuggingFace via the `datasets` library. Script saves ~3 AI and ~3 real images locally, then asserts the model classifies them correctly. If everything inverts, the label-index mapping is wrong — fix and re-run.

**Sources actually used** (after dataset-shopping in Phase 1):
- **AI images:** `Hemg/AI-Generated-vs-Real-Images-Datasets`, `AiArtData` class. Note this dataset is misleadingly named — its labels are `AiArtData` / `RealArt` (AI art vs. hand-painted artwork), not AI-vs-real photos. The AI class is still useful for our purposes.
- **Real images:** `nielsr/CelebA-faces` (real celebrity photographs). Needed because the Hemg dataset's "RealArt" class is paintings, which the photo-trained Ateeqq model flags as AI with >99% confidence — a domain mismatch, not a model bug.

**Datasets that didn't work out** (so future-you doesn't re-try them):
- `competitions/aiornot` — gated, requires HF access request.
- `imagenet-1k` — gated.
- Various `Organika/*`, `Falah/*`, `JamieWithofs/*` AI-detection sets — 404s, not on the Hub.

### 4. Model swappability (detectors package)
The detector logic lives in a `detectors/` package, not a flat `detector.py`:

```
detectors/
  __init__.py      # exports get_detector()
  base.py          # BaseDetector ABC + DetectionResult dataclass
  siglip.py        # SiglipDetector — current model
  registry.py      # name → class map, reads DETECTOR_MODEL env var
detector.py        # thin public façade; singleton wrapping get_detector()
```

**`BaseDetector`** defines one abstract method: `detect(image_path: str) -> DetectionResult`.  
**`DetectionResult`** is a dataclass: `verdict: str`, `confidence: float`, `summary: str`.  
**`registry.py`** maps `"siglip"` → `SiglipDetector`. Reading `DETECTOR_MODEL` from env (default `"siglip"`).  
**`detector.py`** keeps the same public `detect(image_path) -> dict` API so the MCP server and tests don't change.

To swap the model later: add `detectors/newmodel.py`, register it in `registry.py`, set `DETECTOR_MODEL=newmodel` in `.env`.

Add `DETECTOR_MODEL=siglip` to `.env`.

### 5. Two minor adjustments from the original PRD
- **Temp file cleanup:** pull `try/finally` cleanup into Phase 4 from the start (not Phase 5). Three lines, prevents temp-file litter during acceptance testing.
- **Requirements pinning:** pin **minor versions** in Phase 1 (`torch>=2.4,<3`, `transformers>=4.45,<5`). Tighten to exact versions in Phase 5 via `pip freeze > requirements.lock`. Keep `requirements.txt` as the human-edited file.

### 6. Label normalization
`Ateeqq/ai-vs-human-image-detector`'s `id2label` returns short codes (e.g. `ai`/`hum`), not the display strings we post. `SiglipDetector` owns the mapping:

```python
_DISPLAY = {"ai": "AI-Generated", "hum": "Human"}
```

At load time, read `model.config.id2label`, assert every value is a key in `_DISPLAY`, and fail loudly if not (model upgrade safety net). Inference picks the top index, looks up the raw label, then maps through `_DISPLAY`. Any future detector implements the same mapping internally so the rest of the code stays detector-agnostic.

### 7. MCP server URL: full path in `.env`
The MCP streamable HTTP transport mounts at a path, not the bare origin. Put the full URL in `.env`:

```
MCP_SERVER_URL=http://127.0.0.1:8765/mcp
```

Client code uses this verbatim — no path appending magic. Server binds to `127.0.0.1` only (never `0.0.0.0`) because `detect_ai_image` accepts arbitrary local file paths and would become an arbitrary-file-read primitive if exposed.

### 8. Health check: MCP handshake, not HTTP ping
Phase 5's startup check calls `list_tools` over the MCP client with a 2-second timeout. A bare HTTP GET against an MCP HTTP endpoint isn't meaningful — only a real MCP handshake proves the server is up and the tool is registered. Failure → log + `sys.exit(1)`.

### 9. Confidence threshold deferred
`AI_CONFIDENCE_THRESHOLD` is not used in the MVP. Behavior (e.g. "reply *Unclear* when confidence < threshold") is unresolved, and shipping unused config invites bugs. Omit from `.env` entirely until there's a real product reason to add it. Note in README as future work.

### 10. Concurrency
Single-flight detection is fine for a small group. The detector singleton holds the model on MPS; concurrent `detect()` calls share it via a lock in `detector.py` so two near-simultaneous photos queue instead of double-allocating GPU memory. If group volume grows, swap to a worker pool — not now.

> **Implementation note (Phase 2 shipped):** uses `threading.Lock`, not `asyncio.Lock`. `detect()` is sync and runs blocking inference; `asyncio.Lock` can only be acquired from inside a running event loop. `threading.Lock` composes with both sync callers (tests, CLI) and async callers (Phase 3 MCP server, Phase 4 bot — which should dispatch inference via `asyncio.to_thread`). Documented in the `detector.py` module docstring.

---

## Phase 1: Local model inference

**Files:** `test_detector.py`, `download_test_images.py`, `requirements.txt`, `test_images/`

**Steps:**
1. Create `requirements.txt`:
   ```
   torch>=2.4,<3
   transformers>=4.45,<5
   Pillow>=10,<12
   datasets>=2.20,<4
   ```
2. Write `download_test_images.py`:
   - For AI images: stream `Hemg/AI-Generated-vs-Real-Images-Datasets` and filter to the `AiArtData` class; save first 3 to `test_images/ai/`.
   - For real images: stream `nielsr/CelebA-faces` (no label filtering — all rows are real photos); save first 3 to `test_images/real/`.
   - Skip if folder already populated.
   - See Key Decision 3 for why two datasets.
3. Write `test_detector.py`:
   - `pick_device()`: MPS → CUDA → CPU.
   - Load `AutoImageProcessor.from_pretrained("Ateeqq/ai-vs-human-image-detector")` and `SiglipForImageClassification.from_pretrained(...)`.
   - Read `model.config.id2label` to determine which index is AI vs Human — **do not hardcode 0/1**.
   - CLI: `python test_detector.py path/to/image.jpg` → prints verdict + confidence.
4. Verify against all 6 downloaded images; expect ≥5/6 correct. If everything is inverted, the `id2label` mapping is being read wrong — fix it.

**Done when:** `python test_detector.py test_images/ai/0.jpg` prints `Verdict: AI-Generated`; a real image prints `Verdict: Human`. Second run does not re-download weights.

---

## Phase 2: Detector module

**Files:** `detectors/__init__.py`, `detectors/base.py`, `detectors/siglip.py`, `detectors/registry.py`, `detector.py`, updated `test_detector.py`

**Steps:**
1. Create `detectors/base.py`:
   - `DetectionResult` dataclass: `verdict: str`, `confidence: float`, `summary: str`.
   - `BaseDetector` ABC with one abstract method: `detect(image_path: str) -> DetectionResult`. Raise `FileNotFoundError` if missing; `ValueError` if PIL can't open it.
2. Create `detectors/siglip.py`:
   - `SiglipDetector(BaseDetector)` — moves all model loading and `pick_device()` logic from Phase 1 here. Model loads in `__init__`, once per instance.
   - `detect()` runs inference and returns a `DetectionResult`. The `summary` field is formatted exactly as the bot will post it.
3. Create `detectors/registry.py`:
   - `_REGISTRY = {"siglip": SiglipDetector}`.
   - `get_detector(name: str | None = None) -> BaseDetector` — reads `DETECTOR_MODEL` env var (default `"siglip"`), instantiates and returns the matching class. Raises `ValueError` for unknown names.
4. Create `detectors/__init__.py` — re-export `get_detector`, `BaseDetector`, `DetectionResult`.
5. Create `detector.py` (public façade):
   - At **import time**: call `get_detector()` and bind the singleton — this validates `DETECTOR_MODEL` eagerly so an unknown name raises `ValueError` at startup, not on the first photo. (Model weight loading still happens here; that's the cost of eager startup. Acceptable: the bot needs the model loaded before it can serve anyway.)
   - `detect(image_path: str) -> dict` delegates to the singleton, guarded by a lock so concurrent calls queue rather than double-using the model. Returns `{"verdict": ..., "confidence": float, "summary": str}`. (See Key Decision 10: `threading.Lock`, not `asyncio.Lock`.)
6. Update `test_detector.py` to `from detector import detect` and loop over all 6 test images, asserting verdicts.

**Done when:** `python test_detector.py` runs the full battery and reports pass/fail. Model loads exactly once across all 6 calls (add a print-on-load to verify). Setting `DETECTOR_MODEL=bogus` and importing `detector` raises `ValueError` immediately — before any `detect()` call.

---

## Phase 3: MCP server (HTTP transport)

**Files:** `mcp_server/server.py`, `test_mcp_client.py`

**Steps:**
1. Add `mcp>=1.0` to `requirements.txt`. (Shipped against `mcp 1.27.1`.)
2. In `server.py`, use the MCP SDK's **streamable HTTP transport** (not stdio). Concretely: `mcp.server.fastmcp.FastMCP(...)` with `mcp.run(transport="streamable-http")`. Client side: `mcp.client.streamable_http.streamablehttp_client` + `mcp.ClientSession`.
3. Register one tool `detect_ai_image(image_path: str)`:
   - Body calls `detector.detect(image_path)`.
   - Wrap in try/except — any exception returns `{"error": str(e), "verdict": None, "confidence": None}`.
   - Catch `FileNotFoundError` and `PIL.UnidentifiedImageError` distinctly so the bot can produce the right user-facing message (see Phase 4 error matrix).
   - **Implementation detail (shipped):** the detector raises `ValueError(...) from UnidentifiedImageError(...)` — the server inspects `exc.__cause__` and prepends the originating type name to the `error` field (e.g. `"UnidentifiedImageError: cannot identify image file ..."`). The Phase 4 error matrix's string-match on the type name is what makes this work; if you change the envelope format, update Phase 4's bot routing in lockstep.
4. Bind to `127.0.0.1:8765` (loopback only — never `0.0.0.0`; the tool takes a local file path and would be an arbitrary-file-read primitive if exposed). Mount the streamable HTTP transport at `/mcp` (FastMCP's `streamable_http_path` default — leave explicit for clarity). Log each invocation: timestamp, image path, verdict, latency.
5. Write `test_mcp_client.py` using the SDK's HTTP client. Connect to `http://127.0.0.1:8765/mcp`, call the tool against one AI and one real image, print results. (Shipped version also exercises both error paths — missing file and non-image file — to verify the Phase 4 routing assumption end-to-end.)
6. Document the run command at the top of `server.py`: `python -m mcp_server.server`.

**Done when:** Two terminals — one runs the server, the other runs the test client; correct verdicts come back. Killing the client doesn't kill the server.

---

## Phase 4: Telegram bot (polling)

**Files:** `telegram_bot/bot.py`, `.env`, `.env.example`

**Pre-work:** BotFather steps (create bot, disable privacy mode via `/setprivacy`, save token). Add to `.env`:
```
TELEGRAM_BOT_TOKEN=your_token_here
MCP_SERVER_URL=http://127.0.0.1:8765/mcp
DETECTOR_MODEL=siglip
```

(`AI_CONFIDENCE_THRESHOLD` deliberately omitted — see Key Decision 9.)

**Steps:**
1. Add to requirements:
   ```
   python-telegram-bot>=21,<23
   python-dotenv>=1,<2
   ```
2. Configure `logging` at module top with `%(asctime)s %(levelname)s %(message)s` — pulled forward from Phase 5 because the Phase 4 acceptance criterion "bot keeps running after an error" isn't verifiable without logs.
3. In `bot.py`:
   - Load `.env`, instantiate Application with token, register `MessageHandler(filters.PHOTO, handle_photo)`.
   - `handle_photo`:
     - Download largest `PhotoSize` to `NamedTemporaryFile(suffix=".jpg", delete=False)`.
     - Wrap call+reply in `try/finally`; `finally` always `os.unlink()`s the temp file (**pulled forward from Phase 5**).
     - In `try`: call MCP `detect_ai_image` via HTTP client, send `result["summary"]` as a threaded reply (`reply_to_message_id=update.message.message_id`).
     - Map exceptions to user-facing replies per the matrix below; log every photo received, every verdict returned, every error.

   | Situation | Detection | Reply |
   |---|---|---|
   | Inference fails (generic) | MCP `result["error"]` set, or HTTP/transport error | `"⚠️ Could not analyse this image."` |
   | Image download fails | Telegram API exception before MCP call | Silent; log only |
   | Unsupported format (PIL can't open) | MCP error message contains `UnidentifiedImageError` | `"⚠️ Unsupported image format."` |
   | MCP server unreachable | Connection refused / timeout | Log only; no reply (avoids spamming the group if the server is down) |
4. Run with `application.run_polling()`.
5. **Test:** post 3 AI and 3 real images in the test group from two accounts; confirm correct threaded replies; confirm `/tmp` has no leftover files; kill the MCP server mid-test and confirm the bot logs the failure and survives.

> **Assumption:** The MCP server and bot run on the same machine, so passing a local temp file path to `detect_ai_image` works. If the MCP server is ever moved to a separate host, this breaks — the server will need to accept image bytes instead of a path. Not a concern for current scope; note it in `server.py`.

**Done when:** Full round-trip works for any group member's photo; bot survives a forced MCP server crash without dying itself.

---

## Phase 5: Hardening + README

**Files:** updated `bot.py`, `README.md`, `requirements.lock`

**Steps:**
1. **Startup health check:** before `run_polling()`, open an MCP client to `MCP_SERVER_URL` and call `list_tools()` with a 2s timeout. Confirm `detect_ai_image` is in the returned list. On failure (connection refused, timeout, or tool missing), log `MCP server unreachable at <url> — start it with 'python -m mcp_server.server'` and `sys.exit(1)`. A bare HTTP GET would not exercise the MCP protocol and is not sufficient.
2. **Per-call timeout:** wrap MCP HTTP call with a 10s timeout (SDK client accepts a timeout param, or use `asyncio.wait_for`). Timeout → same `"⚠️ Could not analyse this image."` path.
3. **Logging:** already configured in Phase 4 — confirm coverage is complete (photo received, verdict returned, every exception with traceback).
4. **Lock file:** `pip freeze > requirements.lock`. Keep `requirements.txt` as the loose human-edited file; the lock file is for reproducibility.
5. **README.md** sections exactly as the PRD lists (what it does, prereqs, install, configure, run, success output, common errors).
6. **30-min soak test:** leave the bot running, post images periodically, confirm no crashes and no temp file accumulation (`ls /tmp/tmp*.jpg | wc -l` should return to 0 between images).

**Done when:** README walks a fresh user end-to-end in under 15 minutes; soak test passes.

---

## Phase 6: Webhooks (deferred until deployed)

Do not touch until there is a real VPS with HTTPS.

**Steps:**
1. Read `WEBHOOK_URL` from `.env`. If present, use `application.run_webhook(...)`; otherwise `run_polling()`.
2. Set webhook with Telegram once at startup.
3. Use port 8443 unless there's a reason otherwise (no privileged port needed).
4. MCP path is unchanged — only the Telegram-side transport changes.

**Done when:** Setting `WEBHOOK_URL` switches mode with no code changes; removing it falls back to polling; end-to-end detection works identically in both modes.

---

## Switching to GPU later

The `pick_device()` helper already returns `cuda` if `torch.cuda.is_available()`. Moving to a discrete GPU box is a no-op for the code. The model is already `.to(device)` on load. On GPU, inference will be sub-second — consider lowering the Phase 5 timeout floor accordingly.
