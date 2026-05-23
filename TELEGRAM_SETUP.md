# Telegram bot — first-time setup

Step-by-step walkthrough to get the bot replying to photos in a Telegram group. Every step has a verification you can do before moving on. Estimate: 10 minutes.

> **Is this safe?** Yes. BotFather is Telegram's official, verified bot — it never sends links, never asks for your password, never DMs first. The only secret in this whole flow is your bot token; treat it like a password (don't paste in public, don't commit to git). The bot has no access to your personal Telegram account, your filesystem outside `/tmp`, or anything on your network. The local MCP server it talks to is bound to `127.0.0.1` only.

---

## Part 1 — Create the bot in Telegram

### Step 1.1 — Open Telegram

Use either the phone app or [Telegram Desktop](https://desktop.telegram.org/) on your Mac. Either works. The Desktop app is easier for copy-pasting the token.

### Step 1.2 — Find BotFather

1. Tap/click the search icon (magnifying glass) at the top.
2. Type exactly: `BotFather`
3. Look at the results.

**Verify the right one:**
- Username must be exactly **@BotFather**
- Must have a **blue verified checkmark** next to the name
- Member count will be in the millions

If you see multiple results without a checkmark, ignore them — they're impersonators. Click only the one with the checkmark.

### Step 1.3 — Open a chat with BotFather

Click on the verified @BotFather. If you've never messaged it before, you'll see a **START** button at the bottom of the chat. Click it.

If you've messaged it before, the chat opens normally.

### Step 1.4 — Send `/newbot`

Type exactly this into the message box and send:
```
/newbot
```

BotFather replies with something like:
> Alright, a new bot. How are we going to call it? Please choose a name for your bot.

### Step 1.5 — Choose a display name

This is the name people see in chat. Can have spaces, can be anything. Examples:
- `Revelio`
- `My Image Detector`
- `AI Photo Checker`

Type your chosen name and send.

BotFather replies:
> Good. Now let's choose a username for your bot. It must end in 'bot'.

### Step 1.6 — Choose a username

This must be globally unique across all of Telegram, and must end in `bot`. Examples:
- `revelio_detector_bot`
- `nidhi_ai_check_bot`
- `myname_revelio_bot`

Add some random characters if the simple ones are taken.

Type your chosen username and send.

**If it's taken:** BotFather says "Sorry, this username is already taken. Please try something different." Just try another one.

**If it works:** BotFather sends a long message containing a line like:
```
Use this token to access the HTTP API:
1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ-1234567890_abcde
```

The token is the long string after `Use this token to access the HTTP API:`. It has a colon in the middle, contains letters and numbers. **Don't share it anywhere.**

### Step 1.7 — Copy the token

- Tap (mobile) or click (desktop) the token text — it should let you copy it.
- Or long-press / right-click and pick Copy.

Paste it somewhere temporary you can get back to (a Notes app, or just leave the BotFather chat open).

---

## Part 2 — Disable privacy mode (critical, easy to forget)

Without this, the bot only sees messages that start with `/`. It will never see photos. The bot will appear "broken" if you skip this.

### Step 2.1 — Send `/setprivacy`

In the same BotFather chat, send:
```
/setprivacy
```

BotFather replies:
> Choose a bot to change group messages settings.

And shows buttons with your bot(s).

### Step 2.2 — Pick your bot

Click the button with your bot's username (e.g. `@revelio_detector_bot`).

BotFather replies:
> 'Enable' - your bot will only receive messages that either start with the '/' symbol or mention the bot by username.
> 'Disable' - your bot will receive all messages that people send to groups.
> Current status is: ENABLED

And shows two buttons: **Enable** and **Disable**.

### Step 2.3 — Click Disable

Click **Disable**.

BotFather replies:
> Success! The new status is: DISABLED. /help

**Verify:** the words "DISABLED" must appear in BotFather's confirmation. If you don't see them, repeat 2.1.

---

## Part 3 — Create a test group and add the bot

### Step 3.1 — Create a new group

**On mobile (iOS/Android):**
1. Tap the pencil/compose icon (top right on iOS, bottom right on Android)
2. Tap **New Group**

**On desktop:**
1. Click the three-line menu (top left)
2. Click **New Group**

### Step 3.2 — Add a placeholder member, then your bot

Telegram requires at least one other "person" to create a group. Two ways:

**Easiest:** add your bot directly here.
1. In the search/add-members box, type your bot's username (e.g. `revelio_detector_bot`)
2. Your bot appears with its display name. Tap/click to select it.
3. Tap **Next** / **Create**
4. Give the group a name like "AI detector test" → **Create**

If Telegram won't let you create a group with only a bot, add another contact you trust (you can remove them later), create the group, then add the bot via the group settings (next step).

### Step 3.3 — Verify the bot is in the group

Open the group. At the very top is the group name. Tap/click it to open group info.

You should see your bot listed under **Members**, marked as `bot`.

### Step 3.4 (only if step 3.2 made you add a human) — Remove the placeholder

If you added a human contact, you can remove them now:
- Open group info → Members → tap their name → **Remove from group**.

The bot will stay.

---

## Part 4 — Configure `.env` on your Mac

### Step 4.1 — Open a terminal at the project

Open Terminal (or iTerm), then:
```bash
cd /Users/nidhibharani/Developer/github_projects/fake_detector
```

Verify you're in the right place:
```bash
pwd
```
Should print: `/Users/nidhibharani/Developer/github_projects/fake_detector`

### Step 4.2 — Copy the example env file

```bash
cp .env.example .env
```

Verify it exists:
```bash
ls -la .env
```
Should show a file like `-rw-r--r-- 1 nidhibharani staff ... .env`.

### Step 4.3 — Open `.env` in an editor

Use whatever editor you like. For example:
```bash
open -a TextEdit .env
```
Or in VS Code:
```bash
code .env
```
Or nano:
```bash
nano .env
```

You'll see:
```
TELEGRAM_BOT_TOKEN=your_token_here
MCP_SERVER_URL=http://127.0.0.1:8765/mcp
DETECTOR_MODEL=siglip
```

### Step 4.4 — Paste the token

Replace `your_token_here` with the token from BotFather. The line should look like:
```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ-1234567890_abcde
```

**Important:**
- No quotes around the token
- No spaces around the `=`
- No spaces at the end of the line

Save the file. Close the editor.

### Step 4.5 — Sanity check the `.env`

```bash
grep TELEGRAM_BOT_TOKEN .env
```
Should print `TELEGRAM_BOT_TOKEN=` followed by your token. Confirm the token looks right (has a colon, has letters/numbers, no quotes).

### Step 4.6 — Confirm `.env` will not be committed

```bash
git check-ignore .env
```
Should print `.env` (meaning git is ignoring it — good). If it prints nothing, your `.gitignore` isn't set up; ask Claude to fix it.

---

## Part 5 — Start the MCP server

### Step 5.1 — Open a NEW terminal window/tab

Keep your original terminal open; you'll need a second one in Part 6.

In the new window:
```bash
cd /Users/nidhibharani/Developer/github_projects/fake_detector
source .venv/bin/activate
```

After `source`, your prompt should change to show `(.venv)` at the start. That means the venv is active.

Verify:
```bash
which python
```
Should print something ending in `.venv/bin/python` (not `/opt/homebrew/bin/python` or similar).

### Step 5.2 — Run the MCP server

```bash
python -m mcp_server.server
```

You'll see output like:
```
2026-05-23 ... INFO mcp_server: Starting MCP server on http://127.0.0.1:8765/mcp
[SiglipDetector] Loading Ateeqq/ai-vs-human-image-detector on mps ...
INFO:     Started server process [...]
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
```

**Verify:** the line `Uvicorn running on http://127.0.0.1:8765` must appear. If it does, the server is ready.

**Leave this terminal alone.** Don't close it, don't hit Ctrl+C. The server has to keep running. Switch to your other terminal for the next step.

---

## Part 6 — Start the bot

### Step 6.1 — Switch to your other terminal

Go back to your original terminal (or open another new one). You need it to be in the project directory with the venv activated:

```bash
cd /Users/nidhibharani/Developer/github_projects/fake_detector
source .venv/bin/activate
```

Verify `(.venv)` is in the prompt.

### Step 6.2 — Run the bot

```bash
python -m telegram_bot.bot
```

You'll see output like:
```
2026-05-23 ... INFO telegram_bot: Bot starting (polling mode). MCP at http://127.0.0.1:8765/mcp
2026-05-23 ... INFO apscheduler.scheduler: Scheduler started
2026-05-23 ... INFO telegram.ext.Application: Application started
```

**Verify:** the line `Bot starting (polling mode)` must appear. After that, the bot is listening.

If you instead see `ERROR: TELEGRAM_BOT_TOKEN is not set`, your `.env` isn't being read — go back to Part 4.

**Leave this terminal alone too.** Now you have two terminals running: MCP server in one, bot in the other.

---

## Part 7 — Send a test photo

### Step 7.1 — Open your test group in Telegram

The group you created in Part 3.

### Step 7.2 — Post a photo

Pick any photo from your camera roll or download one. Send it like any other Telegram photo (attachment icon → Gallery/Photo → pick → send).

Wait 2–5 seconds.

### Step 7.3 — Look for the reply

The bot should reply in-thread (the reply visibly points back to your photo) with something like:
```
🔍 AI Image Check
Verdict: Human
Confidence: 99.4%
```

(`Human` for a real photo, `AI-Generated` for something from Midjourney/DALL·E/etc.)

### Step 7.4 — Check the logs

Switch to your bot terminal (Part 6). You should see new lines like:
```
2026-05-23 ... INFO telegram_bot: photo received chat=-1001234... user=12345...
2026-05-23 ... INFO telegram_bot: verdict chat=-1001234... user=12345... verdict=Human confidence=0.994
```

And in your MCP server terminal (Part 5):
```
2026-05-23 ... INFO mcp_server: detect_ai_image path=/tmp/tmp....jpg verdict=Human confidence=0.994 (23.4 ms)
```

---

## Part 8 — Stop everything cleanly

When you're done:

### Step 8.1 — Stop the bot

In the bot terminal (Part 6): press **Ctrl+C**. You'll see it shut down cleanly.

### Step 8.2 — Stop the MCP server

In the server terminal (Part 5): press **Ctrl+C**. Same thing.

### Step 8.3 — (Optional) deactivate the venv

```bash
deactivate
```

---

## Troubleshooting

If the bot doesn't reply when you post a photo, find the matching row:

| Symptom | Cause | Fix |
|---|---|---|
| Nothing in bot terminal logs when you post | Privacy mode still enabled | Redo Part 2 — must say `DISABLED` |
| Bot terminal shows `photo received` but no `verdict` line | MCP server not running | Check Part 5 terminal — restart if needed |
| Bot terminal shows `MCP call failed (server unreachable?)` | MCP server died or never started | Restart Part 5 |
| `ERROR: TELEGRAM_BOT_TOKEN is not set` | `.env` is in the wrong place or empty | Redo Part 4 from the project directory |
| `Unauthorized` / `401` in the bot terminal traceback | Token is wrong | Re-copy from BotFather; check no extra spaces in `.env` |
| Bot replies in Telegram but it's `⚠️ Could not analyse this image.` | MCP returned an error — check the MCP terminal log for the actual exception | Likely a corrupt image or unsupported format; try another photo |
| Bot replies but says wrong verdict on every image | Label mapping issue (shouldn't happen — verified by tests) | Capture the log output and report it |

If you hit anything not in the table, save the last ~20 lines from the relevant terminal — that's what's needed to debug.

---

## What to do when you're finished playing

- **Keep the bot:** just stop the processes (Part 8). Restart any time with Parts 5 + 6.
- **Delete the bot:** in BotFather, send `/deletebot`, pick your bot, confirm. The bot account is removed from Telegram; your token becomes invalid; the project files stay untouched.
- **Rotate the token** (if you ever leak it): in BotFather, send `/revoke`, pick your bot. BotFather issues a new token; paste it into `.env`. The old token stops working immediately.
