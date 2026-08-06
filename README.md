# 911 Dispatch Relay

A local desktop tool for **GTA World (RAGE MP RP)**. It reads the chat log your own game client already writes to disk, picks out new **911 chat lines** and **in-game 911 / 311 call cards**, rewrites them into a realistic **LAPD radio dispatch** call-out, speaks it in a female voice with a **radio filter**, and plays it through **your own speakers/headset only**.

It reads **one local file, read-only** - the RAGE MP client's own `.storage` chat log, which the game writes by itself. It does **not** touch the game process, memory, or network, it never writes to that file, and it never broadcasts audio to other players.

---

## Easy install (recommended for most people)

If you just want to use the app and not touch any code, use the ready-made Windows installer from the GitHub repo. **No Python, no terminal.**

1. Go to the repository: <https://github.com/coopik/GTA-W-Dispatch-Relay>
2. Open the **Releases** section on the right-hand side (or the `installer_output` download link in the README there).
3. Download the latest **`911DispatchRelay-Setup-x.x.x.exe`**.
4. Run it. Windows SmartScreen may warn about an unknown publisher - click **More info -> Run anyway** (the installer is built with Inno Setup and is safe; it is your own build).
5. Follow the wizard (it creates Start Menu + desktop shortcuts and an uninstaller).
6. Launch **911 Dispatch Relay** from the Start Menu or desktop.
7. First run: open **Settings** to paste your ElevenLabs (or other) API key, then on the **Dashboard** press **Detect file** followed by **Start**. See the **Tutorial** tab inside the app for a step-by-step walkthrough.

> Your settings (API key, voice, chat log path) are stored in `%APPDATA%\911 Dispatch Relay\config.yaml`, so they survive updates and reinstalls.

> Updating: download and run the newer setup `.exe` over the top - your settings are preserved. You do **not** need Python for this path.

Prefer to run or modify the source code instead? Follow the developer setup in sections 1-8 below.

---

## What it does (pipeline)

1. **Watch** the RAGE MP `.storage` chat log for new lines - instant file notifications, with a polling safety net.
2. **Parse** each line into a clean message: sender, call sign, channel (radio / local / OOC / PM / HQ / dispatch) and the exact text. Multi-line 911 call cards are assembled into one message.
3. **Flag** relevant lines: chat patterns (`911`, `*dials 911*`, `[EMS]`, `[PD]`) and structured **call blocks** (Call ID / Situation / Location / Number).
4. **Rewrite** the flagged text into an LAPD dispatch call-out (offline generator, or an LLM API if you add a key).
5. **Speak** it (ElevenLabs / Edge / Google / pyttsx3), reading numbers digit-by-digit.
6. **Radio filter**: bandpass, static, distortion, key-click.
7. **Play** locally, queuing calls so they never overlap. A short alert tone plays before each dispatch.

---

## 1. Install Python

1. Install **Python 3.10+** (3.11 or 3.12 recommended) from <https://www.python.org/downloads/>.
2. On the installer's first screen, tick **"Add python.exe to PATH"**.
3. Verify in a terminal (PowerShell or CMD):
   ```
   py --version
   ```

> Python 3.13/3.14 removed the built-in `audioop` module that audio needs. This is handled automatically by the `audioop-lts` dependency below, so any modern version works.

---

## 2. Get the project & install dependencies

1. Unzip this folder somewhere easy, e.g. `C:\Users\<you>\Downloads\911 Dispatch Relay\`.
2. Open a terminal **in that folder** (in File Explorer, type `cmd` in the address bar and press Enter).
3. (Recommended) create a virtual environment:
   ```
   py -m venv .venv
   .venv\Scripts\activate
   ```
4. Install the Python packages:
   ```
   py -m pip install --upgrade pip
   py -m pip install -r requirements.txt
   ```

This installs the file watcher, the audio stack, and (on Windows) `pywin32` for the system-tray icon.

---

## 3. Point it at your chat log

RAGE MP saves your in-game chat into a local file named `.storage` (the client's own storage
file). That single file is the app's only input:

```
<RAGEMP install>\client_resources\<32-character hash>\.storage
```

For example:

```
C:\RAGEMP\client_resources\cb242ee11d52ccd84309050503ab5242\.storage
```

The folder name is a hash of the server address, so it is different for every person and every
server - don't copy someone else's path.

1. Start the app and press **Detect file** on the Dashboard. It searches your RAGE MP install and
   picks the `.storage` file whose `server_version` is **GTA World**.
2. If that fails, press **Browse...** and pick the file yourself.
3. The chosen path is saved to `config.yaml` under `input_source.path`.

> **Log in to GTA World at least once before detecting.** The file only exists once the client has
> written its storage. If you play on several RAGE MP servers, the newest matching file wins.

> How it reads: RAGE MP rewrites the whole file instead of appending to it, and trims old chat, so
> the app compares successive snapshots to work out what is new. Only new chat is ever announced,
> and the file is opened read-only.

---

## 4. ffmpeg (audio decoding)

ffmpeg is needed to decode MP3 audio from the TTS services. The `imageio-ffmpeg` dependency bundles a copy automatically, so **you usually do not need to install anything**. If you ever see a `[WinError 2]` audio error, install ffmpeg from <https://www.gyan.dev/ffmpeg/builds/> and add its `bin` folder to PATH.

---

## 5. Voice (TTS) setup

Default provider is **ElevenLabs**. Your API key and voice ID are already in `config.yaml` under `tts.elevenlabs`.

- **Free ElevenLabs plan:** you can only use **your own** voices. Pick a voice ID from your ElevenLabs **VoiceLab / Voices** page and paste it into `tts.elevenlabs.voice_id`. (Library/premade voices return `402 Payment Required` on the free plan.)
- **No API key / fully free:** set `tts.provider: edge`. This uses Microsoft's free neural voices (`en-US-AriaNeural` is a female voice). `edge-tts` is included in `requirements.txt` and is **bundled into the installed .exe automatically** — no manual install needed. (If you run from source, `pip install -r requirements.txt` already covers it.)
- **Google Cloud TTS:** set `tts.provider: google`, install `google-cloud-texttospeech`, and point `tts.google.credentials_json` at your service-account JSON.
- **Offline Windows voice:** set `tts.provider: pyttsx3` (uses the built-in Windows "Zira" female voice, no internet).

Numbers are always spoken **digit-by-digit** (`speak_digits: true`), so "911" becomes "nine one one" and incident "0907" becomes "nine oh seven".

---

## 6. Optional: smarter rewrites with an LLM

The app ships with a **smart offline dispatcher generator** that already:

- **Judges severity** and picks the right response code - **Code 3** (lights and sirens) for anything violent or life-threatening in progress (a woman screaming for help, shots fired, an assault, someone unconscious), and **Code 2** for cold or non-violent reports (a theft that already happened, vandalism, a suspect who already left).
- **Re-states the call in third person** like a real dispatcher instead of parroting the caller ("I'm being followed" becomes "reporting party states they're being followed").
- Applies the **San Andreas Penal Code**, reads only the last four digits of the incident, and never reads the caller's name or phone number.
- Handles **unit radio traffic** (code six, requesting an additional unit, pursuits, officer in distress) separately from 911 calls.

For even more natural, context-aware wording, add any **OpenAI-compatible** API key under `llm`:

```yaml
llm:
  enabled: true
  base_url: https://api.openai.com/v1   # OpenAI
  model: gpt-4o
  api_key: sk-...
```

### Using Groq (fast + free developer tier)

Groq is OpenAI-compatible, so it is a drop-in. Point `base_url` at Groq and use one of its models:

```yaml
llm:
  enabled: true
  base_url: https://api.groq.com/openai/v1
  model: openai/gpt-oss-120b        # or llama-3.3-70b-versatile, openai/gpt-oss-20b
  api_key: gsk_your_groq_key_here
```

> If Groq "does nothing", it is almost always because `model` is still an OpenAI name (like `gpt-4o`) that Groq does not have - the request fails and it silently falls back to the offline generator. Set `model` to a real Groq model as shown above.

The dispatcher persona/instructions live in `llm.system_prompt` in `config.yaml`; leave it blank to use the built-in prompt. Leave `api_key` blank to stay fully offline. If the API fails for any reason, it automatically falls back to the offline generator.

### Optional: AI verification of borderline flags

Detection (deciding *what* to flag) is done by fast local rules on every frame, so it stays free and instant. If you want an extra layer of accuracy, turn on **AI verification** (Settings > Dispatch AI, or `llm.verify_flags: true`). When enabled, borderline flags (911 call cards, generic chat, and radio traffic) are sent to your LLM with a strict yes/no question -- *"is this a real emergency a dispatcher would broadcast, or just on-screen text / an advertisement / a server banner?"* -- before anything is spoken. Structurally-certain events (panic button, code six, CAD updates that already carry a callsign) skip the check for speed, verdicts are cached, and if the API errors or times out the flag is allowed through (fails open) so a real call is never silently dropped. Off by default; requires an `api_key`.

---

## 7. Run it

From the project folder (with the venv active if you made one):

```
py main.py
```

The app opens with a clean, light-theme interface:

- **Sidebar** - switch between **Dashboard**, **Settings**, and **About**.
- **Dashboard** - a big status card (Idle / Listening / Speaking), **Start** / **Stop** buttons, a **Chat log input** card with **Detect file**, **Browse...**, **Test Voice** and **Show Chat**, a live **Recent calls** feed, and an activity log.
- **Settings** - every option from `config.yaml` in one place (voice, dispatch AI, radio effect, chat log input, flagging, playback, alert). Edit and hit **Save** - changes apply immediately (playback device/volume changes apply on restart). There's also a **\u2699 Settings** button on the Dashboard.

Headless mode: `py main.py --cli`. Locate the chat log and exit: `py main.py --detect`.

> The modern UI uses **CustomTkinter** (installed via `requirements.txt`). If it isn't installed, the app automatically falls back to the classic interface, so it always runs.

> If `python main.py` says "module not found", use `py main.py`. Run it from **inside** the project folder so it can find `config.yaml` and the `modules` folder.

> **Want a real installable app instead?** You can package this into a standalone
> `911 Dispatch Relay.exe` and a one-click `Setup.exe` (with Start Menu + desktop shortcuts and an
> uninstaller) - no Python needed for the end user. Just run **`build.bat`** on Windows. Full
> instructions are in **`BUILD.md`**. When installed, your settings live in
> `%APPDATA%\911 Dispatch Relay\config.yaml`, so your API key, voice, and chat log path
> survive updates.

---

## 8. What it watches

Everything comes from the one `.storage` file in section 3. There is **nothing to calibrate** - no
region to drag, no window to pick. The game can be full-screen, minimized, or on another monitor;
it makes no difference, because nothing is read from the screen.

Press **Start**. Use **Test Voice** to confirm audio and the radio filter, and **Show Chat** on the
Dashboard to watch lines being parsed live in the form `(channel) sender: text`.

The parser understands the GTA World chat formats, including:

| Kind | Example |
| --- | --- |
| Radio | `** [S: 1 \| CH: BASE] Kiara Eponimos says: 25M14, clear.` |
| Local speech | `Connor Myer says: Alpr.` (also `shouts:`, `says (to X):`) |
| HQ / duty | `[HQ] Police Officer II Connor Myer has gone on duty under 2W63!` |
| Dispatch tags | `[DISPATCH]`, `[RADAR]`, `[GPS]`, `[EQUIPMENT]` |
| Emergency call card | the five-line `********** EMERGENCY CALL **********` block |
| OOC / PMs | `(( (10) Sergeant II Kayayday: no ))` - detected so they can be ignored |

Radio traffic keeps its **sub-channel** (`BASE`, `TRAFFIC`, `SPLX-1`, `L-TAC1`, `MA-1`) and slot
number, so base radio can be told apart from a tactical channel. Because the text is exact, call
signs and plates are never misread.

---


### Testing without the game

You do not need to be in game, in a server, or even online to test the app. There
are four ways to drive it, easiest first.

**a) The chat simulator (no game, no server).** `tools\simulate_chat.py` writes a
fake `.storage` file and feeds realistic chat into it on a timer, exactly the way
the game client does - radio traffic, local chat, panic calls and full emergency
call cards:

```
cd "C:\path\to\911 Dispatch Relay"
py tools\simulate_chat.py --interval 4
```

It prints the path of the fake file. Paste that into **Settings > Chat log input >
File path**, switch **Auto-detect the file on start** OFF, Save, then press
**Start**. You will hear real dispatch audio for made-up calls. Useful flags:
`--interval 2` (faster), `--no-loop` (play once instead of repeating), `--once` (dump
it all at once), `--list` (just print the scenario). By default it loops until you press
Ctrl+C, which is what you want: the app deliberately ignores whatever was already in the
file when you pressed Start, so chat has to keep arriving while it is listening.

**b) Replay your own real chat log.** The `.storage` file survives after you quit
the game, so yesterday's chat is still sitting on disk. Replay it line by line as
if it were happening live:

```
py tools\simulate_chat.py --from-file "C:\RAGEMP\client_resources\<hash>\.storage"
```

This only ever reads your real file; the simulated copy is written elsewhere. This
is the most realistic test there is, because it is your actual radio channel, your
actual call signs and your actual calls.

**c) `replay_last` against the real file.** Point the app at your real `.storage`
and set `input_source.replay_last: 20` in `config.yaml`. On Start it processes the
last 20 lines already in the file instead of ignoring the backlog. Set it back to
`0` for normal use, or you will re-hear old traffic every time you press Start.

**d) Text-only check, no audio.** `py tools\test_flag.py` pushes sample lines
through the flagger and prints what would have been flagged. Fastest way to test
your call signs and patterns without spending TTS credits.

To test **auto-detection** itself against a fake folder, set the `RAGEMP_ROOT`
environment variable to a folder containing `client_resources\<anything>\.storage`
and press **Detect log**.

## 9. What gets read

**Chat lines** containing your configured patterns (`911`, `*dials 911*`, `[EMS]`, `[PD]`).

**Call cards** like the MDC / in-game 911 panel, e.g.:
```
====== CALL ======
Call ID: #237023
Situation: There's a dead body in the street.
Location: Rockford Hills, West Eclipse, Mad Wayne Thunder
Phone Number: 50947953
```
This becomes something like:
> "All units, a two oh two murder at Rockford Hills, West Eclipse, Mad Wayne Thunder, just occurred. Incident seven oh two three. Code three. Units responding, identify."

Rules applied to call cards:
- **San Andreas Penal Code** is used for the crime (e.g. 202 murder, 215 robbery, 216 armed robbery, 302 burglary, 306 grand theft auto, 207 ADW, 707 shots fired). The mapping lives in `modules/llm.py` (`_INCIDENTS`); the LLM prompt lives in `config.yaml` (`llm.system_prompt`).
- **Call ID is always called the "incident"**, only its **last four digits** are read, and it is spoken every time (works with or without a leading `#`).
- The **location is always included**.
- The **caller's name and phone number are never read**.
- Every dispatch **ends with an LAPD closing** such as "Units responding, identify." or "Any unit to handle, identify." (these rotate).
- **Non-emergency and landline calls are never spoken.** Only genuine emergencies trigger TTS; anything classified as non-emergency (or containing words like "landline" / "non-emergency") is logged but skipped. Turn this off with `llm.emergency_only: false`.
- Toggle the call-card parser with `flagging.call_block.enabled`.

---

## 10. Configuration reference (`config.yaml`)

- **input_source.path**: full path to the RAGE MP `.storage` chat log. Blank = auto-detect.
- **input_source.auto_detect** / **server_fingerprint**: find the file automatically, matching the server name (`GTA World`).
- **input_source.use_watchdog**: instant file-change notifications; `false` = polling only.
- **input_source.poll_interval** / **debounce_ms**: safety-net re-check interval, and how long to wait after a change before reading so a half-written file is never parsed.
- **input_source.retry_attempts** / **retry_delay**: retries for when the game client has the file locked.
- **input_source.replay_last**: re-process this many existing lines on start (`0` = only brand-new chat).
- **location.track_area_from_radio**: learn your current area from your own radio traffic, for area call-outs.
- **flagging.patterns**: regex list.
- **flagging.status_dedup_sec**: seconds a repeated status call ("25T15, clear.") stays suppressed before it may be read again. Default 90. **min_body_length**, **fuzzy_threshold** (dedup strictness), **dedup_history**. **call_block.enabled**: parse call cards.
- **llm**: `enabled`, `base_url`, `model`, `api_key`, `system_prompt` (the LAPD dispatcher persona), `verify_flags` (opt-in AI double-check of borderline flags before dispatch).
- **tts**: `provider`, `speak_digits`, and per-provider settings (`elevenlabs`, `edge`, `google`, `pyttsx3`).
- **radiofx**: `intensity`, `bandpass_low_hz`, `bandpass_high_hz`, `noise_level`, `distortion`, `key_click`.
- **playback**: `device` (null = default), `volume`, `max_queue`.
- **alert**: short tone played before each dispatch (`path`, `volume`, `gap_ms`).
- **ui**: `mode` (`gui`/`cli`), `recent_limit`.

---

## 11. Troubleshooting

- **`No chat log file set`** - press **Detect file** on the Dashboard, or set `input_source.path` by hand (section 3).
- **Nothing is ever read** - the path is wrong, or the client hasn't written its storage yet. Log in to GTA World once, then press **Detect file** again. **Show Chat** tells you whether lines are arriving.
- **Chat arrives late** - RAGE MP flushes the file on its own schedule. Lowering `input_source.debounce_ms` / `poll_interval` helps a little, but the flush interval is set by the game, not the app.
- **`ModuleNotFoundError: pyaudioop` / `audioop`** - run `py -m pip install -r requirements.txt` (installs `audioop-lts` on Python 3.13+).
- **`402 Payment Required` (ElevenLabs)** - free plan; use your own cloned voice ID, or switch `tts.provider` to `edge`.
- **`[WinError 2]`** - ffmpeg missing; `imageio-ffmpeg` should cover it, otherwise install ffmpeg and add to PATH.
- **No audio** - check the **Test** button, `playback.device`, system volume, and that a `dispatch_alert.wav` exists in `assets/`.
- **Old chat is announced when you press Start** - set `input_source.replay_last: 0` so only brand-new lines are read.
- **Numbers sound wrong** - keep `tts.speak_digits: true`.
- **`ModuleNotFoundError: watchdog`** - run `py -m pip install -r requirements.txt`. Without it the app falls back to plain polling, so it still works, just a little less instantly.
- **Call ID / incident not spoken** - make sure the call card has a Call ID line (with or without `#`) and `flagging.call_block.enabled: true`. Only the last four digits are read.
- **A call didn't get read** - if it was classified non-emergency/landline it is skipped by design. Set `llm.emergency_only: false` to read everything.

---

## 12. Installing pywin32 (system tray + monitor placement)

`pywin32` provides the Windows APIs used for the system-tray icon and for opening the window on a chosen monitor. It is Windows-only and already listed in `requirements.txt`, but if those features error out, install it directly:

1. Open a terminal in the project folder (activate your venv if you made one).
2. Install it:
   ```
   py -m pip install pywin32
   ```
3. If you still get import errors (rare), run the one-time post-install step from an **Administrator** terminal (adjust the path to your Python version, or use `.venv\Scripts\pywin32_postinstall.py` if you used a venv):
   ```
   py -m pip install --upgrade pywin32
   python "%LOCALAPPDATA%\Programs\Python\Python312\Scripts\pywin32_postinstall.py" -install
   ```
4. Verify:
   ```
   py -c "import win32gui; print('pywin32 OK')"
   ```

pywin32 is entirely optional - without it you only lose the tray icon and the “open on monitor” preference.

---

## 13. Project structure

```
911 Dispatch Relay/
  main.py               orchestrator + CLI + classic-UI fallback
  config.yaml           all settings
  requirements.txt      dependencies
  README.md             this file
  assets/
    dispatch_alert.wav  alert tone played before each dispatch
  modules/
    gui_app.py          modern CustomTkinter UI (Dashboard / Settings / Report a bug / About)
    file_watcher.py     watches the RAGE MP .storage chat log and parses it into messages
    displays.py         monitor enumeration for window placement
    flagger.py          chat + call-card detection and dedup
    llm.py              LAPD dispatch rewriting (offline + API)
    reporter.py         redacted, rate-limited bug / error reporting via Discord webhook
    tts.py              text-to-speech + digit verbalization
    radiofx.py          radio filter
    player.py           queued local playback
    mdc_lookup.py       optional MDC Lookup Assistant (rate-limited worker)
    mdc_auth.py         optional manual browser login + encrypted session (DPAPI)
    mdc_parser.py       optional HTML parsing of MDC results
```

### Does the anti-flagger need an API key?

**No.** All the flagging and dispatch logic — 911 chat/MDC card detection, dedup, panic, CAD updates, code six, code seven, clear/back-in-service, and the LAPD radio wording — is 100% local (regex + heuristics + an offline generator). It works perfectly with **no API key at all**. A Dispatch AI key is optional and only adds LLM-polished rewrites and the opt-in "AI verification of borderline flags" feature.

### Dispatch acknowledgements (code seven & clear)

- **Code seven** (out of service / meal): "25T15, show me code seven" or "25T15, code seven at Pershing Square" → acknowledged with rotating LAPD wording.
- **Clear** (back in service): "25T15, show me clear", "25T15, clear", or "25T15, show me available" → acknowledged with rotating LAPD wording.
- Both are on by default and configurable under **Settings > Flagging** (scope: your own call signs or all units).

---

## 14. Optional: MDC Lookup Assistant

> **This module is optional and OFF by default.** It is separate from everything above and does nothing until you configure it and switch it on.

**What it does:** listens for spoken "run this name / plate" requests it sees on your screen, looks them up in **GTA World's Web MDC** (the browser system at <https://mdc.gta.world/> - *not* the game), and reads the result back over the radio voice. It is strictly **read-only** - it only performs searches and never edits anything.

### ⚠ Read this before enabling

- **Terms of Service / ban risk.** Automating a logged-in website may violate GTA World's rules on third-party tools and automation. Enabling this is entirely at your own risk, on your **own account only**. If you are not comfortable with that risk, leave it off.
- **It will not work out of the box.** GTA World's real MDC search URLs and page markup are not shipped with the app (they're private, logged-in pages). The `mdc_lookup.name_search_url`, `mdc_lookup.plate_search_url`, and `mdc_lookup.selectors` values in `config.yaml` are **placeholders you must fill in yourself** by inspecting the live site with your browser's DevTools (Network + Inspect). Until you do, lookups will fail gracefully and speak nothing useful.

### How the login works (your password is never stored)

1. Go to **Settings > MDC Lookup (optional) > Log in**.
2. A real browser window opens to <https://mdc.gta.world/>. **You** log in there yourself, exactly as you normally would.
3. When you're logged in, close the browser window. The app captures only the resulting **session cookies** and stores them **encrypted with Windows DPAPI** (tied to your Windows user account) in a separate file. Your username and password are never seen or stored.
4. **Log out** clears that stored session at any time.

### Configuring it

In **Settings > MDC Lookup (optional)**:

- **Enable MDC lookups** - master switch (keep off until configured).
- **Lookups apply to** - `own` reacts only when one of your own call signs asks for the run; `all` reacts to any unit.
- **Cooldown** - minimum seconds between requests (default 8). Please don't lower this recklessly.
- **Response channel label** - optional text spoken before each result (e.g. "TAC 2").
- **Name / Plate lookup phrases** - the trigger regexes, one per line. Each name pattern must contain a `(?P<target>...)` group; each plate pattern a `(?P<plate>...)` group. Defaults recognise phrases like *"...let me get a code ten on John Doe"*, *"run John Doe for me dispatch"*, *"look up a plate GHX829"*, and *"run plate GHX829"*.

The search URLs, HTML selectors, login-page markers, cooldown, queue size and timeout live under the `mdc_lookup:` block in `config.yaml` (each line is commented).

### Dependencies

This module needs two extra packages (already in `requirements.txt`) plus a one-time browser download:

```
py -m pip install beautifulsoup4 playwright
py -m playwright install chromium
```

The Chromium browser used for the manual login is **not** bundled inside the packaged `.exe`; the `playwright install` step downloads it locally.

### Safety built in

- **Read-only** - only performs searches, never writes.
- **Rate limited** - at most one request per cooldown, a small bounded queue (overflow dropped + logged), and exponential backoff on errors.
- **Session-expiry aware** - if your MDC session expires, it announces "Web MDC session expired - please log in again" and stops, without crashing or looping.
- **Local request log** - a rotating `mdc_requests.log` (timestamp, type, target) is kept in your app data folder.

---

## Legal / fair use

For personal use on a single machine. It only reads visible pixels and produces local audio, like a person reading chat aloud. It does not read game memory/files/network, performs no automated in-game actions, and does not broadcast audio to anyone else. Follow your server's rules on third-party tools.
