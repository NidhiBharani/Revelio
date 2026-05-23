# Implementation Phases: Telegram AI Image Detection Bot

Each phase is independently completable and testable before moving to the next. Do not start a phase until the previous one has a passing definition of done.

---

## Phase 1: Model Inference (Local Script)

**Goal:** Get the detection model running on your machine and confirm it returns correct results. No bot, no MCP, no Telegram. Just the model.

### What to build

A standalone Python script (`test_detector.py`) that:
- Loads the `Ateeqq/ai-vs-human-image-detector` model from HuggingFace
- Accepts a local image file path as a CLI argument
- Prints the verdict and confidence score to the console

### Acceptance criteria

- Running `python test_detector.py some_image.jpg` prints something like:
  ```
  Verdict: AI-Generated
  Confidence: 94.2%
  ```
- Works on at least one AI-generated image and one real photo
- Model weights download automatically on first run and are cached (no re-download on second run)
- Script runs without errors on CPU (no GPU needed)

### Dependencies to install

```
torch
transformers
Pillow
datasets
```

### Notes for Claude Code

- Model ID: `Ateeqq/ai-vs-human-image-detector`
- Use `AutoImageProcessor` and `SiglipForImageClassification` from `transformers`
- Use `pick_device()`: MPS if `torch.backends.mps.is_available()`, then CUDA, then CPU — do not hardcode CPU
- Do not hardcode label indices — read `model.config.id2label` to determine which index maps to AI vs Human
- Apply softmax to logits to get confidence scores

---

## Phase 2: Detector Module

**Goal:** Refactor Phase 1 into an abstraction layer that makes the model swappable, then expose a stable public API for the MCP server and bot to call.

### What to build

A `detectors/` package that separates the interface from the implementation, plus a thin `detector.py` façade that the rest of the project imports:

```
detectors/
  __init__.py       # re-exports get_detector, BaseDetector, DetectionResult
  base.py           # BaseDetector ABC + DetectionResult dataclass
  siglip.py         # SiglipDetector — wraps the current HuggingFace model
  registry.py       # maps DETECTOR_MODEL env var to the right class
detector.py         # public façade: singleton detect(image_path) -> dict
```

**`base.py`** defines:
```python
@dataclass
class DetectionResult:
    verdict: str        # "AI-Generated" | "Human"
    confidence: float
    summary: str        # formatted string the bot posts verbatim

class BaseDetector(ABC):
    @abstractmethod
    def detect(self, image_path: str) -> DetectionResult: ...
```

**`siglip.py`** implements `BaseDetector`. Model loads once in `__init__`. Raises `FileNotFoundError` / `ValueError` for bad paths.

**`registry.py`** reads `DETECTOR_MODEL` from env (default `"siglip"`), instantiates the matching class. Raises `ValueError` for unknown names.

**`detector.py`** keeps the same public API so nothing else changes:
```python
def detect(image_path: str) -> dict:
    # Returns {"verdict": ..., "confidence": float, "summary": str}
```

To swap the model later: add `detectors/newmodel.py`, register it in `registry.py`, set `DETECTOR_MODEL=newmodel` in `.env`.

### Acceptance criteria

- `detector.py` can be imported and `detect()` called from another Python file
- Model is loaded exactly once across all calls (add a print-on-load to verify)
- Returns a dict with `verdict`, `confidence` (float), and `summary` (formatted string)
- Raises a clear exception if the image path doesn't exist or can't be opened
- Setting `DETECTOR_MODEL` to an unknown value raises a clear `ValueError` at *import time* of `detector.py`, not on the first `detect()` call (eager singleton — see implementation plan, Key Decision 4)
- A simple `test_detector.py` that imports and calls `detect()` still works

### File structure at end of phase

```
project/
  detectors/
    __init__.py
    base.py
    siglip.py
    registry.py
  detector.py
  test_detector.py
  requirements.txt
```

---

## Phase 3: MCP Server

**Goal:** Wrap the detector module in an MCP server that exposes `detect_ai_image` as a callable tool.

### What to build

`mcp_server/server.py` that:
- Starts an MCP server on localhost
- Exposes one tool: `detect_ai_image`
- The tool accepts `image_path` (string) as input
- Calls `detector.detect()` and returns the result as a JSON-serialisable dict

### Acceptance criteria

- MCP server starts without errors: `python -m mcp_server.server`
- The `detect_ai_image` tool can be called from an MCP client and returns the correct result
- Server logs each incoming request to the console
- Server does not crash if inference fails; returns an error dict instead:
  ```json
  { "error": "Could not process image", "verdict": null, "confidence": null }
  ```

### Testing this phase

Write a small test client (`test_mcp_client.py`) that connects to the running server, calls `detect_ai_image` with a local image path, and prints the response. You should be able to verify the full round trip without Telegram.

### Dependencies to add

```
mcp   # official MCP Python SDK
```

### File structure at end of phase

```
project/
  mcp_server/
    server.py
  detector.py
  test_detector.py
  test_mcp_client.py
  requirements.txt
```

---

## Phase 4: Telegram Bot (Polling)

**Goal:** A working Telegram bot that listens to a group, detects images, and replies with a verdict. This is the first end-to-end working version.

### Pre-requisites (do before writing any code)

1. Create a bot via BotFather on Telegram (`/newbot`)
2. Save the bot token
3. Add the bot to your test group as a member
4. In BotFather, run `/setprivacy` for your bot and set it to **Disabled** so it can read all group messages, not just commands
5. Add token to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   MCP_SERVER_URL=http://127.0.0.1:8765/mcp
   DETECTOR_MODEL=siglip
   ```
   (`AI_CONFIDENCE_THRESHOLD` is deferred — see implementation plan, Key Decision 9.)

### What to build

`telegram_bot/bot.py` that:
- Reads `TELEGRAM_BOT_TOKEN` from environment
- Starts a polling loop using `python-telegram-bot`
- Listens for any group message that contains a photo
- Downloads the highest-resolution version of the photo to a temp file
- Calls the MCP server's `detect_ai_image` tool with the temp file path
- Replies to the original image message with the formatted summary
- Deletes the temp file after the reply is sent (always — `try/finally`, pulled forward from Phase 5)
- Logs each photo received, each verdict returned, and each error with `logging` (pulled forward from Phase 5 — needed to verify the "survives errors" acceptance below)

> **Note:** The bot passes a local temp file path to the MCP server's `detect_ai_image` tool. This works because both processes run on the same machine. If the MCP server is ever moved to a separate host, the tool will need to accept image bytes instead of a path.

### Reply format

```
🔍 AI Image Check
Verdict: AI-Generated
Confidence: 94.2%
```

### Error handling

| Situation | Detection | Bot behaviour |
|---|---|---|
| Inference fails (generic) | MCP returns `result["error"]`, or HTTP error | Reply: "⚠️ Could not analyse this image." |
| Image download fails | Telegram API exception before MCP call | Silent fail, log only |
| Unsupported format | MCP error mentions `UnidentifiedImageError` (server raises this distinctly — see plan Phase 3 step 3) | Reply: "⚠️ Unsupported image format." |
| MCP server not running | Connection refused / timeout | Log only, no reply (avoid spamming the group) |

### Acceptance criteria

- Post a photo in the test group: bot replies within 5 seconds
- Reply is threaded to the original image message
- Bot keeps running after an error (no crashes)
- Bot ignores non-image messages silently
- Works for images posted by any group member, not just the bot owner

### Dependencies to add

```
python-telegram-bot
python-dotenv
```

### File structure at end of phase

```
project/
  detectors/
    __init__.py
    base.py
    siglip.py
    registry.py
  mcp_server/
    server.py
  telegram_bot/
    bot.py
  test_images/
    ai/
    real/
  detector.py
  download_test_images.py
  test_detector.py
  test_mcp_client.py
  .env
  .env.example
  requirements.txt
  README.md
```

---

## Phase 5: Hardening and README

**Goal:** Make the project reliable enough that someone else (or future you) can set it up cleanly and the bot doesn't need babysitting.

### What to build

**Robustness fixes:**
- Add a startup check: open an MCP client to `MCP_SERVER_URL`, call `list_tools()` with a 2s timeout, confirm `detect_ai_image` is registered. On failure log a clear error (including the URL and `python -m mcp_server.server` hint) and `sys.exit(1)`. A bare HTTP GET is not sufficient — MCP HTTP doesn't expose one.
- Add a timeout to MCP calls (default 10 seconds); if inference takes longer, treat it as a failure
- (Temp file cleanup and console logging already in place from Phase 4 — verify coverage; no new work)

**README.md covering:**
- What the project does (two sentences)
- Pre-requisites (Python version, BotFather steps, privacy mode)
- How to install dependencies
- How to configure `.env`
- How to run (two terminal commands)
- What a successful run looks like
- Common errors and fixes (privacy mode not disabled, MCP server not running, model download slow)

### Acceptance criteria

- A fresh clone of the project can be set up and running in under 15 minutes following only the README
- Bot runs continuously for 30 minutes in a test group without crashing
- All temp files are cleaned up after each image processed
- Console output makes it clear what the bot is doing at each step

---

## Phase 6: Webhook Mode (Future)

**Goal:** Replace polling with webhooks so the bot can run on a server and receive events in real time instead of continuously asking Telegram for updates.

> This phase requires a public HTTPS URL. Do not start until the bot is deployed to a VPS or server.

### What changes

- Add a `WEBHOOK_URL` config option to `.env`
- In `bot.py`, detect whether `WEBHOOK_URL` is set and switch between polling and webhook mode automatically
- Polling remains the default for local development; webhooks activate only when `WEBHOOK_URL` is present
- Server needs to expose port 443, 80, 88, or 8443 (Telegram requirement)

### Acceptance criteria

- Setting `WEBHOOK_URL` in `.env` switches the bot to webhook mode with no code changes
- Removing `WEBHOOK_URL` falls back to polling
- End-to-end image detection still works identically in both modes

---

## Summary

| Phase | What you get | Testable without |
|---|---|---|
| 1 | Model runs locally | Telegram, MCP |
| 2 | Clean detector module | Telegram, MCP |
| 3 | MCP server with tool | Telegram |
| 4 | Full working bot (polling) | Nothing, this is the MVP |
| 5 | Reliable, documented | Nothing |
| 6 | Production-ready webhooks | Local machine |
