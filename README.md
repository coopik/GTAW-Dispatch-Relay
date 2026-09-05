# 911 Dispatch Relay

**Version 1.6.0**

An AI LAPD radio dispatcher for GTA World / FiveM roleplay. It watches your game
chat log, spots 911 calls and unit radio traffic, writes a realistic LAPD
dispatch broadcast, and reads it aloud over a radio-effect voice.

```
game chat log  ->  flagger  ->  brain  ->  Smart Dispatch  ->  voice  ->  your speakers
                (find it)   (is it real?)  (write it)      (say it)
```

---

# Table of contents

**Getting started**
1. [Quick start (5 minutes)](#1-quick-start-5-minutes)
2. [Install Python](#2-install-python)
3. [Install the app](#3-install-the-app)
4. [Point it at your chat log](#4-point-it-at-your-chat-log)
5. [Install ffmpeg](#5-install-ffmpeg)
6. [Run it](#6-run-it)

**Voice**
7. [Voice setup and the four providers](#7-voice-setup)
8. [ElevenLabs: getting a key and the exact permissions](#8-elevenlabs-key-and-permissions)
9. [Keeping the voice consistent](#9-keeping-the-voice-consistent)

**Smart Dispatch**
10. [What Smart Dispatch is and how it works](#10-what-smart-dispatch-is)
11. [Getting an AI API key](#11-getting-an-ai-api-key)
12. [Turning Smart Dispatch on](#12-turning-smart-dispatch-on)
13. [Choosing a model, and what it costs](#13-models-and-cost)

**Features**
14. [Your call signs and "only answer my call sign"](#14-call-signs-and-scope)
15. [The Brain: what gets read and what does not](#15-the-brain)
16. [Streets, districts and RDs](#16-streets-districts-and-rds)
17. [Alarms, including vehicle alarms](#17-alarms)
18. [MDC Lookup Assistant](#18-mdc-lookup-assistant)

**Reference**
19. [Full config reference](#19-full-config-reference)
20. [Testing without the game](#20-testing-without-the-game)
21. [Troubleshooting](#21-troubleshooting)
22. [Performance tuning](#22-performance-tuning)
23. [Project structure](#23-project-structure)
24. [Legal / fair use](#24-legal--fair-use)

---

# 1. Quick start (5 minutes)

If you just want it working with zero keys and zero cost:

1. Run the installer (`911DispatchRelay-Setup-1.6.0.exe`) **or** follow
   [section 2](#2-install-python) and [section 3](#3-install-the-app).
2. Launch **911 Dispatch Relay**.
3. Go to **Settings > Input source** and click **Auto-detect**.
4. Go to **Settings > Unit call-outs** and type your call signs, e.g. `25T15`.
5. Click **Start** on the Dashboard.

That's it. You are now running on the **free** voice (Edge Neural) and the
**free offline** dispatch writer. No API keys, no bills, no accounts.

Add keys later only if you want:

| You want | You need | Cost |
|---|---|---|
| It working at all | nothing | free |
| Smarter, more varied call-outs | an AI key ([section 11](#11-getting-an-ai-api-key)) | free tier available |
| A specific premium voice | an ElevenLabs key ([section 8](#8-elevenlabs-key-and-permissions)) | free tier available |

---

# 2. Install Python

**Skip this if you used the installer .exe.**

1. Download Python **3.10 or newer** from <https://www.python.org/downloads/>.
2. Run the installer.
3. **Tick "Add python.exe to PATH"** on the first screen. This is the single
   most common setup mistake. If you miss it, nothing below works.
4. Verify in a new Command Prompt:

```bat
python --version
```

You should see `Python 3.10.x` or higher.

---

# 3. Install the app

```bat
cd "C:\path\to\911 Dispatch Relay"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Every time you open a new Command Prompt to run the app, re-run
`.venv\Scripts\activate` first. Your prompt shows `(.venv)` when it is active.

### Optional extras

```bat
pip install pywin32     # system tray + multi-monitor placement
pip install keyboard    # global Start/Stop hotkeys
pip install rapidfuzz   # ~10x faster street-name typo matching
```

`rapidfuzz` is worth installing. The app works without it (it falls back to
Python's built-in matcher), but street correction gets noticeably faster.

---

# 4. Point it at your chat log

The app reads a **text log your game writes to disk**. It never touches game
memory, never injects code, and never sends keystrokes into the game.

## The easy way

**Settings > Input source > Auto-detect.** Done in most cases.

## The manual way

You need a chat logger. The supported one is the **GTAW Log Parser (FiveM)**,
which writes to:

```
%LOCALAPPDATA%\GTAW-Log-Parser-FiveM\current-session.txt
```

Paste that into **Settings > Input source > Chat log path**.

### Checking it works

1. Start the log parser and leave it running.
2. Stand somewhere busy in game so chat scrolls.
3. Open the file in Notepad. You should see lines like:

```
[19:42:11] Someone says: help, there's a guy with a gun outside!
[19:42:30] ** [S: 1] Dispatch: 25T15, respond to Innocence Boulevard **
```

If the file is empty or missing, the problem is the **log parser**, not this
app. Fix that first.

### Screen-capture mode (fallback)

If your server has no log parser, **Settings > Input source > Screen capture**
reads chat with OCR off your screen. It is slower and less accurate. Use the
log file whenever you can.

---

# 5. Install ffmpeg

Needed to decode audio from ElevenLabs and Google. **If you only use the free
Edge voice you can skip this.**

1. Download a Windows build from <https://www.gyan.dev/ffmpeg/builds/>
   (`ffmpeg-release-essentials.zip`).
2. Extract it, e.g. to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your PATH.
4. Verify in a **new** Command Prompt:

```bat
ffmpeg -version
```

Or just drop `ffmpeg.exe` in the app folder next to `main.py`.

---

# 6. Run it

```bat
.venv\Scripts\activate
python main.py
```

The GUI opens. Click **Start**.

CLI mode, if you prefer no window:

```bat
python main.py --cli
```

### What you should see

```
[19:42:11] Watching C:\Users\you\AppData\Local\GTAW-Log-Parser-FiveM\current-session.txt
[19:42:33] FLAGGED: Incident 4471: guy with a gun outside the store @ Innocence Boulevard
[19:42:34] DISPATCH: All units, a 706 brandishing at Innocence Boulevard. RP reports a
           male armed with a handgun outside a store. Incident four four seven one.
           R D, thirteen fifty two. Code 3 emergency. Units responding, identify.
```

If you see `FLAGGED` but no `DISPATCH`, your voice provider failed. See
[section 21](#21-troubleshooting).

---

# 7. Voice setup

Four providers. Set with `tts.provider` or in **Settings > Voice**.

| Provider | Key needed? | Cost | Quality | Notes |
|---|---|---|---|---|
| `edge` | No | Free | Very good | **Default.** Microsoft neural voice, needs internet |
| `pyttsx3` | No | Free | Poor/robotic | Fully offline Windows SAPI. Emergency fallback |
| `elevenlabs` | Yes | Free tier, then paid | Best | Most realistic dispatcher |
| `google` | Yes | Paid | Very good | Google Cloud TTS |

The default `edge` provider is genuinely good and costs nothing. Only move to
ElevenLabs if you want a specific voice.

### Recommended radio effect

Leave `radiofx.enabled: true`. It band-passes the voice to 300-3000 Hz and adds
mic clicks and static, which is what actually makes it sound like a police
radio. A clean studio voice sounds far less convincing than a slightly crunchy
one.

---

# 8. ElevenLabs key and permissions

## Step 1: Make an account

Go to <https://elevenlabs.io> and sign up. The free tier gives you roughly
10,000 characters per month, which is around 100 short call-outs.

## Step 2: Create the API key

1. Click your **profile icon** (bottom-left).
2. Choose **API Keys**.
3. Click **Create API Key**.
4. Name it something like `Dispatch Relay`.

## Step 3: Set the permissions - THIS IS THE IMPORTANT PART

ElevenLabs keys are scoped. A key with the wrong scopes returns **HTTP 401**,
and older versions of this app then silently switched to a different voice,
which is exactly why some users heard the dispatcher change character
mid-shift.

Set the scopes like this:

| Scope | Setting | Why |
|---|---|---|
| **Text to Speech** | **Has access** | Required. This is the only scope the app actually calls |
| **Voices** | Read only *(optional)* | Only lets the app list your voices in Settings |
| **Models** | Read only *(optional)* | Only lets the app list available models |
| User | No access | Not needed |
| History | No access | Not needed |
| Dubbing | No access | Not needed |
| Voice Cloning | No access | Not needed |
| Projects / Studio | No access | Not needed |
| Sound Generation | No access | Not needed |
| Workspace | No access | Not needed |

**Minimum viable key: Text to Speech = Has access. Everything else off.**

Also set:

- **Character quota limit**: optional, but setting e.g. `10000` means a runaway
  loop can never burn your whole balance.
- **Restrict key to specific voices**: optional, recommended. Restrict it to
  the one dispatcher voice you use.

Copy the key immediately. ElevenLabs shows it **once**.

## Step 4: Pick a voice ID

1. Go to **Voices** in the ElevenLabs sidebar.
2. Pick or add a voice. For a dispatcher, a calm, level American voice works
   best. Avoid "expressive" or "characterful" voices; they over-act.
3. Click the voice, then **ID** to copy its voice ID (a string like
   `pYduSEMlSc5NZ5UXU4aO`).

## Step 5: Put it in the app

**The safe way (recommended)** - set an environment variable so your key never
sits in a config file you might share:

```bat
setx ELEVENLABS_API_KEY "your-key-here"
```

Then close and reopen your Command Prompt.

**The direct way** - in `config.yaml`:

```yaml
tts:
  provider: elevenlabs
  elevenlabs:
    api_key: ''            # leave blank to use the env var above
    voice_id: pYduSEMlSc5NZ5UXU4aO
    model_id: eleven_turbo_v2
    stability: 0.85
    similarity_boost: 0.75
    style: 0.0
    use_speaker_boost: true
    speed: 1.0
    seed: 20250905
    timeout: 30
```

> **Never commit a real key.** If you ever share your `config.yaml`, a zip, or a
> screenshot of it, treat that key as burned and rotate it in the ElevenLabs
> dashboard immediately.

## Which model?

| Model | Latency | Use it when |
|---|---|---|
| `eleven_turbo_v2` | Lowest | **Recommended.** Dispatch needs to be fast |
| `eleven_multilingual_v2` | Higher | You need non-English |
| `eleven_monolingual_v1` | Higher | Legacy |

---

# 9. Keeping the voice consistent

If your dispatcher used to sound calm on one call, rushed on the next, and
occasionally like a chipmunk, that was three separate causes. All three are
fixed in 1.6.0, and these are the settings that control them.

```yaml
tts:
  allow_fallback: true      # see below
  normalize_audio: true     # equalise loudness across all call-outs
  output_sample_rate: 24000 # one rate for every provider - kills pitch shifts
```

### `allow_fallback`

When your provider fails, the app can fall back `edge` -> `pyttsx3`. Those are
**different voices**, so a rate-limited or unscoped ElevenLabs key produced a
different-sounding dispatcher on every failed call.

- `true` - always get audio, but the voice may change if your provider fails.
- `false` - **pin one voice.** If it fails you get a clear log line and silence
  for that call instead of a stranger's voice.

Set it to `false` if voice consistency matters more to you than never missing a
call.

### `stability: 0.85`

This is the ElevenLabs setting that was really causing the "fast and excited vs
slow" problem. At the old `0.5`, ElevenLabs re-interprets the emotion of each
request, so identical text is performed differently every time. `0.85` holds
the delivery flat and repeatable, which is what a real RTO sounds like.

Also keep `style: 0.0`. Style is emotional exaggeration; a dispatcher has none.

### `seed`

A fixed integer seed makes ElevenLabs generate near-identical delivery for
identical text. Change it only if you want to reroll the voice's character.

### The chipmunk bug

Providers return audio at different sample rates (16 kHz to 48 kHz). Audio
played at the wrong rate is pitch-shifted - 48 kHz audio played as 24 kHz is
the chipmunk voice. Everything is now resampled to a single
`output_sample_rate` before playback, so this cannot happen.

### Text is flattened too

Even with a locked voice, `Shots fired!!!` and `ARMED AND DANGEROUS` make any
TTS engine speed up and raise pitch. The app now flattens `!!!`, `...`, `--`
and SHOUTED WORDS before synthesis, while preserving real abbreviations like
`RD`, `TAC`, `EMS`, `LAPD` and `BOLO`.

---

# 10. What Smart Dispatch is

**Smart Dispatch is the AI layer that turns a panicked player's chat message
into a professional LAPD radio broadcast.**

## The problem it solves

A player types:

> `Someone says: OH MY GOD there's a dude with a knife chasing a woman down the street near little soeul please help!!!`

Reading that aloud is useless. Smart Dispatch produces:

> *All units, a 207 assault with a deadly weapon in progress at Little Seoul. RP
> reports a male armed with a knife pursuing a female on foot. Incident four
> four seven one. R D, oh two seventy two. Code 3 emergency. Units responding,
> identify.*

## The pipeline

```
1. FLAGGER    Is this line even a 911 call or radio traffic?
              (channel filters, chat structure, dedup, your scope rules)
                            |
2. BRAIN      Is it a real incident, or OOC chatter / a prank / a hang-up?
              Offline scoring. No AI, no tokens, instant.
                            |
3. GEO        Fix the location typo. "little soeul" -> "Little Seoul".
              Generate the RD for that location.
                            |
4. SMART      Write the broadcast: pick the penal code section, judge
   DISPATCH   Code 2 vs Code 3, summarise in third person, add the
              incident number and RD, choose a closing.
                            |
5. VOICE      Clean the text for speech, synthesise, add radio effect, play.
```

## Two engines, and this matters

Step 4 runs one of two engines:

**A. The offline generator (default, free)**
A hand-written LAPD call-out builder. It matches the incident against ~60 San
Andreas Penal Code sections, decides the response code, corrects the location,
attaches the RD, and varies its openings and closings. It needs no key, costs
nothing, and never rate-limits. It is genuinely good, just more formulaic.

**B. The AI rewrite (optional, needs a key)**
Sends the situation to an LLM with a detailed LAPD RTO system prompt. Handles
unusual calls the offline generator has no template for, and phrases things
more naturally. This is what most people mean by "Smart Dispatch".

**The AI never runs alone.** The offline generator always produces a call-out
first. If the AI is off, fails, times out or returns junk, you still hear a
proper broadcast. This is why the app has no single point of failure.

---

# 11. Getting an AI API key

You need **one** of these. Groq is the best starting point: it is fast and has
a genuinely usable free tier.

## Option A: Groq (recommended, free tier)

1. Go to <https://console.groq.com>.
2. Sign up (Google/GitHub login works).
3. Click **API Keys** in the sidebar.
4. Click **Create API Key**, name it `Dispatch Relay`.
5. Copy it. It starts with `gsk_`.

```yaml
llm:
  enabled: true
  provider: openai_compatible
  base_url: https://api.groq.com/openai/v1
  model: llama-3.3-70b-versatile
  api_key: 'gsk_your_key_here'
  max_tokens: 400
  reasoning_effort: low
  timeout: 20
  emergency_only: true
```

## Option B: OpenAI

1. Go to <https://platform.openai.com>.
2. Sign up, then **Settings > Billing** and add credit. OpenAI has **no free
   tier**; $5 lasts a very long time at this usage.
3. Go to **API Keys > Create new secret key**.
4. Under permissions choose **Restricted**, and grant only:
   - **Model capabilities: Write** (this is what `/chat/completions` needs)
   - Everything else: **None**
5. Copy the key. It starts with `sk-`.

```yaml
llm:
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini
  api_key: 'sk-your_key_here'
```

## Option C: A local model (free, private, no internet)

Run [Ollama](https://ollama.com) or LM Studio, then:

```yaml
llm:
  base_url: http://localhost:11434/v1
  model: llama3.1:8b
  api_key: 'ollama'      # any non-empty string
  timeout: 60            # local models are slower
```

Keeps everything on your machine and costs nothing, but needs a decent GPU.

---

# 12. Turning Smart Dispatch on

### In the GUI

1. **Settings > Smart Dispatch (AI)**
2. Tick **Enable AI rewrites**
3. Paste your API key
4. Set the **Base URL** and **Model** for your provider ([section 11](#11-getting-an-ai-api-key))
5. Click **Test connection**
6. **Save**

### In `config.yaml`

```yaml
llm:
  enabled: true
  provider: openai_compatible
  base_url: https://api.groq.com/openai/v1
  model: llama-3.3-70b-versatile
  api_key: 'gsk_...'
  max_tokens: 400
  reasoning_effort: low
  tac_referral: true
  timeout: 20
  emergency_only: true
  repeat_location: true
```

### Verifying it is actually running

Turn on `ui.debug: true` and watch the console. AI-rewritten call-outs are
logged differently from offline ones. Or use **Speak test** on the Dashboard.

If the AI is silently not being used, check in this order:

1. `llm.enabled` is `true`
2. `api_key` is non-empty
3. `base_url` matches your provider **and ends in `/v1`**
4. `model` is a model your key can actually access
5. `emergency_only` - if `true`, routine Code 2 calls deliberately skip the AI
   to save tokens. Set `false` to use AI on everything.

### Key settings explained

| Setting | Meaning |
|---|---|
| `emergency_only: true` | Only spend tokens on emergencies. Routine calls use the free offline generator |
| `max_tokens: 400` | Ceiling per call-out. Keep high; reasoning models get cut off mid-sentence otherwise |
| `reasoning_effort: low` | For reasoning models. `low` keeps hidden reasoning short so the spoken text is not truncated |
| `timeout: 20` | Seconds before giving up and using the offline call-out |
| `tac_referral: true` | Adds "refer to TAC-1" on priority calls |
| `repeat_location: true` | LAPD realism. The RTO says the address twice for clarity over the radio ("at Grove Street, Grove Street"). Set `false` to state it once |
| `system_prompt` | Override the built-in LAPD RTO prompt entirely. Leave unset unless you know what you're doing |

#### Why the location is said twice

This is intentional, not a glitch. Real LAPD RTOs double-call the address so a
unit that missed it the first time over engine noise or a stepped-on
transmission still gets it:

> All units, a 211 in progress **at Grove Street, Grove Street**. ...

It is the same reason a unit's call sign is repeated ("1 Adam 12, 1 Adam 12").
Both the offline generator and the AI prompt do this. If you would rather hear
the address once, set `repeat_location: false`; the typo correction, RD and
everything else are unaffected.

---

# 13. Models and cost

| Model | Provider | Speed | Quality | Cost |
|---|---|---|---|---|
| `llama-3.3-70b-versatile` | Groq | Very fast | Great | Free tier |
| `gpt-4o-mini` | OpenAI | Fast | Great | ~$0.0001/call |
| `gpt-4o` | OpenAI | Medium | Best | ~$0.002/call |
| `llama3.1:8b` | Ollama (local) | Depends on GPU | Good | Free |

A call-out is roughly 700 tokens in and 120 out. Even on `gpt-4o`, a long
session costs cents. With `emergency_only: true` you cut that further.

---

# 14. Call signs and scope

This is the setting behind the "it flags everybody's code six" bug, so it is
worth understanding properly.

## Setting your call signs

**Settings > Unit call-outs > Your call signs**, or:

```yaml
location:
  callsigns: ["25T15", "1-Adam-12"]
```

Formatting is flexible. Phonetic words are expanded to letters before
comparison, so every row below is understood as the **same unit**:

| You can type | Read on air as |
|---|---|
| `1A12`, `1-Adam-12`, `1 Adam 12`, `1adam12` | one Adam twelve |
| `25T15`, `25 Tom 15`, `25-Tom-15` | twenty-five Tom fifteen |
| `2A55`, `2 Adam 55`, `2 Alpha 55` | two Adam fifty-five |
| `R13` | Robert thirteen |
| `3D31` | three David thirty-one |

### Canine units

Canine call signs are supported in every common spelling, and all of these
resolve to the same unit:

| You can type | Read on air as |
|---|---|
| `K9-1`, `K9 1`, `K9 one`, `Canine 1`, `canine one` | K nine one |
| `K9 CH4`, `K9 channel 4` | K nine four |
| `R30K9` | Robert thirty K nine |

A canine unit is always read **"K nine"**, never "King nine" or "Kilo nine".

NATO spellings are accepted and folded onto the LAPD word for the same letter,
so typing `2 Alpha 55` is still read "two Adam fifty-five". Mixing forms is
fine: if you list `25T15`, a transmission from `25 Tom 15` still matches.

## What `scope` does

Every unit-traffic feature has a `scope`:

- `own` - only react to **your** call signs
- `all` - react to every unit on the channel

```yaml
flagging:
  code_six:
    enabled: true
    scope: own
```

## The bug that was fixed in 1.6.0

With `scope: own`, code six was still being read for **everyone**. Two things
were wrong:

1. Call-sign matching was loose, so `1A12` could match other units' signs.
   It is now an exact match after phonetic normalisation.
2. **The real cause:** when the code-six parser correctly decided "this is not
   my unit", the line fell through to the generic radio-traffic handler at the
   end of the pipeline, which announced it anyway. The pipeline now records
   that a feature deliberately refused a line, and the catch-all handler skips
   it.

So `scope: own` now actually means own.

## Code six: backup vs additional

Going code six marks you out for investigation, but the app also reads the rest
of the transmission and grades the response code from it.

| What the unit says | Response | Alert tone |
|---|---|---|
| `code six on Grove Street` | Code 2 | no |
| `...requesting an additional unit` | Code 2 | no |
| `...requesting a supervisor` / `an air unit` | Code 2 | no |
| `...requesting backup` | **Code 3** | yes |
| `...need help` / `assistance` / `a cover unit` | **Code 3** | yes |
| `...I've got a body on the ground` | **Code 3** | yes |

**Backup is not the same as an additional unit.** Backup (also help,
assistance, a cover unit, expedite) is an emergency and goes out Code 3:

> All units, one Adam twelve is requesting backup at Grove Street. Code 3, units
> responding, identify.

An additional unit is routine and goes out Code 2:

> Additional unit requested at Elgin Avenue, any available unit, Code 2.

You do not have to ask for anything for the app to escalate. Emergencies
mentioned in passing are detected in the body of the transmission, so:

> 25 Tom 15, code six on Adam's Apple, I've got a body on the ground

is broadcast Code 3 with the alert tone, even though no backup was requested.
The same applies to man down, unresponsive, not breathing, no pulse, DOA, GSW,
gunshot, bleeding, stabbed, hostage, overdose, a weapon drawn and a fight in
progress.

## `require_callsigns`

```yaml
flagging:
  require_callsigns: false
```

- `false` (default) - with **no** call signs configured, `own` answers every
  unit. Convenient, but it is the old confusing behaviour.
- `true` - `own` means exactly your list. With an empty list, nothing is
  flagged.

If you set any scope to `own`, **fill in your call signs.** If you don't, the
app warns you, because `own` with an empty list is almost never what you meant.

---

# 15. The Brain

New in 1.6.0. The flagger finds *candidates*; the brain decides whether a
candidate is a *real incident* worth radio traffic.

Before, anything matching a keyword got read out. So the dispatcher solemnly
broadcast OOC chatter, hang-ups, prank calls, "what time does the station
open", and the same robbery four times.

## How it scores

Fully offline, deterministic, instant, zero tokens.

**Adds points for:** weapons, violence, medical emergencies, fire,
in-progress wording, property crime, traffic collisions, disturbances, a usable
location, and a detailed report.

**Subtracts points for:** out-of-character chatter (`((`, `//`, `ooc`, `afk`,
`lol`), tests and cancellations ("this is a test", "disregard", "false alarm",
"wrong number"), information requests ("how do I file", "pay a ticket"),
hang-ups and dead air, and routine quality-of-life complaints.

**Rejects outright:** bare acknowledgements (`hey`, `copy`, `10-4`), keysmash
spam, anything too short to be an incident, and duplicates of a call already
broadcast in the last two minutes.

## Config

```yaml
brain:
  enabled: true
  threshold: 18            # score needed to broadcast
  priority_threshold: 50   # score that counts as a priority
  repeat_window_sec: 120   # duplicate suppression window
  require_location: false  # true = never broadcast without a location
  min_letters: 12
  log_decisions: false
```

## Tuning it

Set `log_decisions: true` and watch the console. Every suppression is logged
with its reason:

```
[brain] suppressed: out-of-character chatter
[brain] suppressed: no dispatchable content (score 10 < 18)
[brain] suppressed: duplicate of a call already broadcast
```

- Still reading noise? Raise `threshold` to 25-35.
- Skipping calls you wanted? Lower it to 10-15.
- Want everything back? `enabled: false`.

## Reading unit radio traffic (new in 1.6.0)

The brain also reads what *units* say on the radio, in plain English, with no
code word required. Before 1.6.0 you had to say "code six" or "shots fired"
before the app would react to anything at all; `25T15, I need backup on Calais.`
produced nothing.

Every line of unit traffic is now graded on three questions:

| Question | What it looks for |
| --- | --- |
| **What is being asked for?** | Backup -> Code 3. An additional unit, supervisor or air unit -> Code 2. |
| **What happened?** | 19 incident categories - officer needs help, hostage, shooting, stabbing, pursuit, weapon, robbery, medical, violence, fire, burglary, collision, vehicle, impaired driver, disturbance, theft, suspicious, traffic stop, in custody. Recognised from plain English *and* from penal codes (187, 211, 207, 242, 415, 459, 10851, 23152...). |
| **Where?** | Resolved against the street and district gazetteer, so typos are corrected and the RD can be worked out. |

In-progress wording (`in progress`, `right now`, `active`) and escalators
(`multiple`, `several`, `crowd`, `gang`) raise the grade. So:

```
25T15, I need backup on Calais.
  -> All units, twenty-five Tom fifteen is requesting backup at Calais,
     Calais. R D, fourteen fifty five. Code 3, respond emergency and identify.

25T15, active brawl at Hawick's Clothing, roll backup
  -> All units, twenty-five Tom fifteen reports a fight in progress at
     Hawick's Clothing, Hawick's Clothing and is requesting backup.
     R D, twelve twenty one. Code 3, respond emergency and identify.

2 Adam 55, requesting an additional unit at Elgin Avenue
  -> Additional unit requested for two Adam fifty-five at Elgin Avenue,
     Elgin Avenue. R D, oh six oh five. Any available unit to handle,
     Code 2, identify.
```

Note that **backup is always read as a priority** and never needs a request
verb - `backup on Calais` counts on its own - because missing a backup request
is far worse than announcing one. An additional unit is only a request when an
actual request verb introduces it, so `anyone know where the supervisor is`
is chatter, not a request for a supervisor.

Out-of-character chatter is rejected outright, whatever it contains. Turn the
whole thing off with `flagging.radio_traffic: false`.

**One behaviour change worth knowing:** radio traffic is not filtered by
`scope`, so a *different* unit asking for backup will still be broadcast even
when your other features are set to `scope: own`. That is deliberate - relaying
backup requests to everyone is the dispatcher's job - and it is what "watch the
whole chat log" means. `code_six` and the other unit-traffic acknowledgements
still honour `scope` exactly as before.

## What bypasses the brain

Unit traffic - code 6, panic, CAD updates, clear, code 7, OPG, EOW, out status,
MDC and alarms - **always** bypasses the brain, because your `scope` settings
already decided whether you want to hear it.

Radio traffic is the one exception: it is graded by the intent reader described
above rather than by the 911-call lexicon, because that lexicon knows nothing
about "roll backup" and scored such lines at zero. The 911-call scoring below
applies to 911 calls and chat reports.

---

# 16. Streets, districts and RDs

New in 1.6.0.

## Typo correction

The app ships a gazetteer of **242 streets, 85 districts and 46 landmarks**
across Los Santos and Blaine County, plus the numbered highways.

Callers misspell things constantly. Locations are now corrected **before**
anything is spoken:

| Caller typed | Dispatcher says |
|---|---|
| Little Soeul | Little Seoul |
| Vinwood Blvd | Vinewood Boulevard |
| Innocense Blvd | Innocence Boulevard |
| Sandy Shorez | Sandy Shores |
| Paleto Bey | Paleto Bay |
| Del Pero | Del Perro |
| Maze Bank Towr | Maze Bank Tower |

It also expands abbreviations (`Blvd` -> `Boulevard`, `St` -> `Street`) and
formats intersections (`Alta & Spanish` -> `Alta Street and Spanish Avenue`).

Crucially, it **refuses to guess**. Nonsense like `asdkjhasd`, `my house` or a
vehicle model like `Tavros` does not match a street, so the app falls back to
"refer to CAD for location" rather than inventing somewhere.

```yaml
geo:
  enabled: true
  correct_typos: true
  threshold: 0.78   # raise to 0.85 for conservative, lower to 0.70 for aggressive
  speak_rd: true
```

## RDs (reporting districts)

Real LAPD broadcasts close with the incident number and the reporting district:

> *"...Incident 171 in RD 193."*

Every 911 call-out with a location now ends the same way:

> *All units, a 302 burglary at Power Street. ... Incident four one two two.
> **R D, oh one forty six.** Code 2. Units to handle, identify.*

The rules, exactly as specified:

- Always spoken as the letters **"R D"**, never the words "reporting district".
- Always **exactly four digits**.
- Spoken in natural two-and-two pairs, not four separate digits:

| RD | Spoken |
|---|---|
| 1313 | thirteen thirteen |
| 4051 | forty fifty one |
| 2010 | twenty ten |
| 1300 | thirteen hundred |
| 0105 | oh one oh five |

- RDs are **invented but stable**: the same location always gets the same RD,
  for the whole session and across restarts. `Grove St` and `Grove Street` get
  the same RD, and so do `Little Soeul` and `Little Seoul`. First two digits
  are derived from the district's LAPD division, so nearby streets get related
  RDs.

---

# 17. Alarms

```yaml
flagging:
  alarms:
    enabled: true    # property alarms
    vehicle: true    # vehicle alarms from security firms
```

## The vehicle alarm bug (fixed in 1.6.0)

In-game security firm notifications look like:

```
Security Firm: vehicle alarm was set off on Tavros closest street: Alta Street
```

The app used to take the text after "set off on" as the location, so it
broadcast **"location Tavros"** - and Tavros is a motorcycle, not a place.

There is now a gazetteer of about **400 GTA V vehicle models**. The parser:

1. Identifies the vehicle model and reports it **as the vehicle**.
2. Prefers the `closest street:` value as the location.
3. Rejects any location candidate that is a known vehicle model.
4. Prefers candidates that match a real street or district.

| Input | Location | Vehicle |
|---|---|---|
| `set off on Tavros closest street: Alta Street` | Alta Street | Tavros |
| `set off on a Sultan RS, closest street: Vinewood Boulevard` | Vinewood Boulevard | Sultan RS |
| `set off on Akuma closest street: Power Street` | Power Street | Akuma |
| `set off on Little Seoul closest street: Decker Street` | Decker Street | - |

Vehicle alarms are now **on by default**, since they work correctly.

---

# 18. MDC Lookup Assistant

Optional. Lets units run name and plate lookups over the radio.

> **Read this first.** It logs into the GTA World MDC on your behalf. Only use
> it on an account you control, and only if your server permits it. Your
> password is **never stored** - it is held in memory for the session and used
> once to obtain a session cookie.

```yaml
mdc_lookup:
  enabled: false
  scope: own
  username: ''
  # password is entered in the GUI at runtime, never saved to disk
```

Enable it in **Settings > MDC Lookup**, enter credentials, and it answers
"Dispatch, run a name on ..." style requests. Needs `requests` and
`beautifulsoup4`. Rate limits are built in.

---

# 19. Full config reference

`config.yaml` lives in the app folder; your edited copy lives in
`%APPDATA%\911 Dispatch Relay\config.yaml`.

### `flagging`

| Key | Default | What it does |
|---|---|---|
| `patterns` | `911`, `[EMS]`, `[PD]`... | Regexes that mark a line as a 911 call |
| `require_callsigns` | `false` | `true` = `own` means exactly your list |
| `min_body_length` | `6` | Ignore shorter messages |
| `fuzzy_threshold` | `0.82` | Duplicate-detection sensitivity |
| `dedup_history` | `400` | Lines remembered for dedup |
| `status_dedup_sec` | `90` | Suppression window for repeated status calls |
| `dedup_cooldown_sec` | `0` | Keep `0` to avoid re-reading re-rendered chat |
| `radio_traffic` | `true` | Read unit-to-dispatch traffic, including plain-language requests with no code word |
| `ignore_channels` | pm, ooc, me, do... | Channels never treated as radio |
| `require_chat_structure` | `true` | Strict: needs real chat structure. Stops log noise |
| `call_block.enabled` | `true` | Parse MDC 911 call cards |
| `skip_own_names` | `[]` | Character names to ignore |
| `panic_button` | `true` | React to panic-button alerts |
| `cad_updates` / `code_six` / `clear_ack` / `code_seven` / `opg` / `end_of_watch` / `out_status` | on, `scope: own` | Unit-traffic features |
| `alarms.enabled` / `alarms.vehicle` | `true` / `true` | Property and vehicle alarms |

### `brain`

See [section 15](#15-the-brain).

### `geo`

See [section 16](#16-streets-districts-and-rds).

### `llm` (Smart Dispatch)

See [section 12](#12-turning-smart-dispatch-on).

### `tts`

See [sections 7-9](#7-voice-setup).

### `radiofx`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `true` | Radio effect on/off |
| `intensity` | `0.6` | Overall strength |
| `bandpass_low_hz` | `300` | Low cut |
| `bandpass_high_hz` | `3000` | High cut |
| `noise_level` | `0.004` | Background static |
| `distortion` | `0.35` | Clipping/grit |
| `key_click` | `true` | Mic key clicks |

### `alert`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `true` | Alert tone before call-outs |
| `scope` | `all` | `all` = every call-out; `priorities` = **only** Code 3 / officer-in-distress |
| `path` | `assets/dispatch_alert.wav` | Your own WAV works here |
| `volume` | `0.9` | Tone volume |
| `gap_ms` | `150` | Silence between tone and speech |

**The `priorities` bug (fixed in 1.6.0):** priority used to be re-guessed by
pattern-matching the finished speech, and that pattern included words like
`burglary`, `fire`, `crash` and `threat`. So a cold Code 2 burglary report was
classified as a priority and the tone played. The app now uses the response
code the dispatcher actually broadcast - Code 3 means priority, Code 2 does
not. `priorities` finally means priorities.

### `playback`

| Key | Default | What it does |
|---|---|---|
| `device` | `null` | Output device (pick in Settings) |
| `volume` | `1.0` | Master volume |
| `max_queue` | `12` | Max queued call-outs before dropping |

### `ui`

| Key | Default | What it does |
|---|---|---|
| `mode` | `gui` | `gui` or `cli` |
| `theme` | `light` | `light` or `dark` |
| `recent_limit` | `20` | Rows in the call feed |
| `open_monitor` | `0` | Which display to open on |
| `sidebar_collapsed` | `false` | Start with icon-only sidebar |
| `debug` | `false` | Live diagnostics console |
| `minimize_to_tray` | `false` | Minimize to tray (needs pywin32) |

### `updates`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `true` | Allow update checks at all |
| `check_on_start` | `true` | Check quietly when the app opens |
| `manifest_url` | GitHub releases API | Where to look for releases |
| `allow_prerelease` | `false` | Also offer pre-release builds |
| `allow_reinstall` | `true` | Offer a rebuilt release that has the same version number |
| `timeout` | `15` | Seconds to wait for the update server |

`allow_reinstall` exists because releases get rebuilt under the same tag. With
it `true`, the startup check tells you when the published v1.6.0 build is newer
than the one you installed. Set it `false` if you only want to hear about
higher version numbers; pressing **Check for updates** by hand still forces the
reinstall either way.

---

# 20. Testing without the game

You do not need to be in game to test.

### Speak test

**Dashboard > Speak test.** Confirms voice, radio effect and playback.

### Feed it fake calls

```bat
python tools/simulate_chat.py
```

Writes realistic fake chat to a temp log. Point **Settings > Input source** at
that file and click Start.

### Test the flagger only

```bat
python tools/test_flag.py
```

Shows which lines are flagged and what dispatch text they produce - no audio,
no API calls.

### Try one line by hand

```bat
python tools/speak_util.py "there's a guy with a gun outside on little soeul"
```

Good for checking typo correction and RD output.

---

# 21. Troubleshooting

### Nothing is flagged

1. Is the log file actually growing? Open it in Notepad.
2. Is your channel in `ignore_channels`? PM/OOC/me/do are ignored by design.
3. Is `require_chat_structure: true` too strict for your server? Try `false`.
4. Turn on `brain.log_decisions: true` - the brain may be suppressing it.
5. Turn on `ui.debug: true` and watch the console.

### It flags too much

Raise `brain.threshold` to 25-35. Add channels to `ignore_channels`. Add
character names to `skip_own_names`.

### Code six / clear is read for other units

Fixed in 1.6.0 - make sure you are actually on 1.6.0. Then set your call signs
([section 14](#14-call-signs-and-scope)); `scope: own` with an empty list
answers everyone unless `require_callsigns: true`.

### The alert tone plays on routine calls

Fixed in 1.6.0. Confirm `alert.scope: priorities`.

### Update says "You are up to date" but the fix is not there

Fixed in 1.6.0. The old check only installed a **strictly higher** version
number, so a release rebuilt and re-uploaded under the same tag was refused and
the button appeared to do nothing.

Press **Check for updates** manually. A manual check now always offers the
newest published build, even at the same version number, and tells you it is a
reinstall. If it says the release has no installer attached, the release was
published without the `.exe`, so open the release page and grab it by hand.

Still stuck? Confirm `updates.enabled: true` and that `updates.manifest_url`
points at your repository. Update installs are Windows-only and only work from
an installed build, not when running from source.

### Code six with backup is not raising the alert

Fixed in 1.6.0. Backup is graded Code 3 and additional units Code 2
([section 14](#14-call-signs-and-scope)). Confirm `alert.scope` is `priorities`
or `all`, and that `flagging.code_six.enabled` is `true`.

### A canine unit is not being recognised

Fixed in 1.6.0. `K9 one`, `K9-1`, `K9 CH4`, `canine 1` and `R30K9` are all
understood now. Add whichever form you use to your call signs.

### The voice keeps changing / sounds like a chipmunk

Fixed in 1.6.0. Also set `tts.allow_fallback: false` to pin one voice, and keep
`stability: 0.85` and `style: 0.0` ([section 9](#9-keeping-the-voice-consistent)).

### No audio at all

1. **Speak test** on the Dashboard.
2. Check `playback.device` in Settings.
3. `pip install sounddevice numpy`
4. For ElevenLabs/Google, confirm `ffmpeg -version` works.

### ElevenLabs 401 Unauthorized

Your key lacks the **Text to Speech** scope, or it was revoked. Recreate it per
[section 8](#8-elevenlabs-key-and-permissions).

### ElevenLabs 429

Out of monthly characters, or rate-limited. Check your ElevenLabs usage page,
or switch to `provider: edge` which is free.

### Smart Dispatch is not being used

See the checklist in [section 12](#12-turning-smart-dispatch-on). Most often
`base_url` is missing `/v1`, or `emergency_only: true` is routing routine calls
to the offline generator by design.

### The location is wrong

Raise `geo.threshold` to `0.85` so only near-perfect typos are corrected.

### Tray icon / monitor placement missing

```bat
pip install pywin32
```

Then restart. If you installed Python from the Microsoft Store, reinstall it
from python.org; the Store build blocks pywin32.

---

# 22. Performance tuning

The app is light - a few percent CPU idling. If you need more headroom:

| Change | Effect |
|---|---|
| `pip install rapidfuzz` | ~10x faster street matching |
| `llm.emergency_only: true` | Far fewer API calls |
| `llm.enabled: false` | No network latency; offline generator only |
| `radiofx.enabled: false` | Skips audio filtering |
| `ui.debug: false` | No diagnostics overhead |
| `flagging.dedup_history: 200` | Slightly less memory |
| `playback.max_queue: 6` | Drops backlog faster during a busy scene |
| Use the log file, not screen capture | OCR is by far the most expensive input mode |

Built-in optimisations in 1.6.0: street lookups are indexed and LRU-cached
(instant on repeat locations); the brain is pure regex with no network calls;
RD generation is a hash, not a lookup; and duplicate suppression stops the same
incident being sent to the AI twice.

---

# 23. Project structure

```
911 Dispatch Relay/
  main.py                 App entry point, pipeline orchestration
  config.yaml             All settings
  README.md               This file
  CHANGELOG.md            Version history
  BUILD.md                How to build the .exe and installer
  requirements.txt        Python dependencies
  modules/
    flagger.py            Finds 911 calls and radio traffic; scope rules
    brain.py              Decides what deserves radio traffic        [NEW 1.6.0]
    geo.py                GTA V streets/districts, typo fixing, RDs   [NEW 1.6.0]
    vehicles.py           GTA V vehicle model gazetteer               [NEW 1.6.0]
    llm.py                Smart Dispatch: offline generator + AI rewrite
    tts.py                Voice synthesis, text cleanup, normalisation
    radiofx.py            Radio band-pass, static, key clicks
    player.py             Audio output queue
    gui_app.py            The GUI
    file_watcher.py       Tails the chat log
    nui_capture.py        Screen-capture/OCR input
    mdc_parser.py         Parses MDC 911 call cards
    mdc_lookup.py         MDC Lookup Assistant
    mdc_auth.py           MDC login (password never stored)
    reporter.py           Bug reporting
    hotkeys.py            Global Start/Stop hotkeys
    displays.py           Monitor enumeration
    icons.py              UI icons
    updater.py            Update checks
    app_paths.py          Version + paths
    usage.py              Token/usage tracking
  tools/
    test_flag.py          Flagger test harness
    simulate_chat.py      Fake chat generator
    speak_util.py         Speak one line from the CLI
    test_mdc.py           MDC parser tests
  assets/
    dispatch_alert.wav    Alert tone
    app.ico               App icon
```

---

# 24. Legal / fair use

- Reads a **log file your own game client writes**. No memory reading, no code
  injection, no automation of gameplay.
- It is an accessibility and immersion aid. It does not play the game for you.
- Check your server's rules before using it. Some servers restrict dispatch
  tools. That is their call, not this app's.
- Not affiliated with Rockstar Games, GTA World, or the Los Angeles Police
  Department. LAPD codes and procedures are used for roleplay realism only.
- **Never share your `config.yaml`** if you put keys in it. Prefer the
  environment variables in [section 8](#8-elevenlabs-key-and-permissions).
