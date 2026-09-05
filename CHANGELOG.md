# Changelog

> **Version history was reset at 1.4.0.** The app was rebuilt from the ground up around a
> completely new input system, and every entry before 1.4.0 described a version that no longer
> exists - different modules, different config, different dependencies. Keeping those notes would
> only be misleading, so they have been removed entirely. 1.4.0 is the first release of the
> rebuilt app.

## 1.6.0

A bug-fix and feature release focused on the four things users kept reporting:
the alert tone firing on routine calls, code six scope leaking other units, the
voice changing character mid-shift, and vehicle alarms reading a car model as a
location. Plus three new subsystems and a redesigned interface.

### The brain now reads plain-language unit traffic (no code word needed)

Typing `25T15, I need backup on Calais.` produced nothing at all. Neither did
`25T15, active brawl at Hawick's Clothing, roll backup`. You had to say "code
six" before the app would react to anything you said on the radio.

Two independent faults stacked up:

1. **The radio parser was a keyword whitelist.** A transmission only counted as
   radio traffic if it literally contained `code six`, `shots fired`,
   `in pursuit`, `roll me`, and so on. `roll backup` was not in the list, and
   neither was `brawl`, so the second line was discarded before anything else
   ran.
2. **`radio` was not on the brain's bypass list.** Anything that did survive
   the parser was then scored with the 911-call lexicon, which contains no
   backup-request signal whatsoever. A pure backup request scored **0**, and
   was suppressed with `no dispatchable content (score 0 < 18)`.

There is now a real intent reader (`modules/intent.py`) that reads every line
of unit traffic the way a dispatcher would, and grades it on three questions:

- **What is being asked for?** Backup (Code 3) or an additional unit (Code 2).
- **What happened?** Nineteen incident categories, from officer-needs-help and
  hostage down to traffic stops and one-in-custody, recognised from plain
  English *and* from penal codes (187, 211, 207, 242, 415, 459, 10851, 23152).
- **Where?** Resolved against the street/district gazetteer, so typos are
  corrected and the reporting district can be worked out.

In-progress wording (`in progress`, `right now`, `active`) and escalators
(`multiple`, `crowd`, `gang`) raise the grade. Out-of-character chatter is
rejected outright, and information requests are not treated as requests for
units, so `anyone know where the supervisor is` stays off the air.

Both of the reported lines now broadcast:

```
25T15, I need backup on Calais.
  -> All units, twenty-five Tom fifteen is requesting backup at Calais,
     Calais. R D, fourteen fifty five. Code 3, respond emergency and identify.

25T15, active brawl at Hawick's Clothing, roll backup
  -> All units, twenty-five Tom fifteen reports a fight in progress at
     Hawick's Clothing, Hawick's Clothing and is requesting backup.
     R D, twelve twenty one. Code 3, respond emergency and identify.
```

Because the intent reader already knows the incident, the location and the
request, the broadcast now names all three plus the RD and the response code,
instead of reading the unit's own words back at it.

### Reporting districts survive the AI rewrite

The Test Voice call, and every real call, could lose its RD. RDs are worked out
deterministically from the location, but when an API key is configured the
finished call-out is passed to the model for a rewrite, and the model
paraphrases freely - frequently dropping the RD, and sometimes the incident
number with it. The offline call-out had the RD all along; the rewrite was
throwing it away.

The RD is now re-attached after any rewrite that lost it, and never doubled up
when it is already there. Officer-distress and pursuit broadcasts include the
RD too, and pursuits now explicitly say "Code 3".

### Fixed: pursuit locations swallowed a word

`suspect is fleeing on foot on Calais Avenue` was broadcast as "in pursuit at
**foot on** Calais Avenue". The pursuit branch scraped the location out of the
raw text with its own matcher instead of using the gazetteer-corrected one.
All radio broadcasts now prefer the resolved location.

### The alert tone no longer plays on non-priority calls

With `alert.scope: priorities`, the tone still played on ordinary Code 2 calls.

The priority was decided correctly when the call-out was written, then thrown
away and re-guessed by pattern-matching the finished speech. That pattern
matched `burglary`, `fire`, `crash`, `threat` and `traffic collision`, so a cold
burglary report already correctly graded Code 2 was re-classified as a priority
on its way to the speaker.

The response code the dispatcher actually broadcast is now carried through the
pipeline to the alert stage. Code 3 means priority; Code 2 does not. The keyword
fallback was deleted rather than patched, because guessing was the bug. When the
priority genuinely cannot be determined, the call is treated as routine instead
of assumed urgent.

### code six with scope own no longer flags everybody

Two separate faults stacked on top of each other.

1. Call-sign comparison was a loose prefix match, so `1A12` could match another
   unit's sign. It is now an exact match, and phonetic forms are normalised
   first, so `1-Adam-12`, `1 Adam 12`, `1adam12` and `1A12` are all recognised
   as the same unit.
2. The actual cause: when the code-six parser correctly decided "this is not my
   unit", it returned nothing, and the line then fell through to the generic
   radio-traffic handler at the end of the pipeline, which announced it anyway.
   Every scope-gated feature had this hole.

The pipeline now records when a feature has deliberately refused a line, and the
catch-all handler skips those lines instead of re-announcing them. All eight
scope-gated features (CAD updates, code six, clear, code seven, OPG, end of
watch, out status, MDC) route through one shared gate.

If a scope is set to `own` and no call signs are configured, the app now reports
that state instead of silently answering every unit.

### The voice no longer changes tone, speed or pitch

Three independent causes, all fixed:

- Silent provider fallback. A failing ElevenLabs key fell back to Edge and then
  to Windows SAPI, three completely different voices. That is the "fast and
  excited, then slow, then very bad" report. New `tts.allow_fallback` setting:
  leave it on to always get audio, or turn it off to pin one voice and get a
  clear log line on failure instead of a stranger's voice. Failed ElevenLabs
  requests now explain themselves, including specific messages for 401 (the key
  is missing the Text to Speech permission) and 429 (quota).
- Unlocked ElevenLabs voice settings. Only `stability` and `similarity_boost`
  were sent, so ElevenLabs re-acted the emotion of every request. Default
  stability raised 0.5 to 0.85, `style` pinned to 0, `use_speaker_boost`
  enabled, and a fixed `speed` and `seed` added.
- The chipmunk voice. Providers return audio at 16-48 kHz, and audio played at
  the wrong rate is pitch-shifted. Everything is now resampled to a single
  `output_sample_rate` (24 kHz) and loudness-normalised, so pitch cannot shift
  and volume no longer jumps between call-outs. Verified across 16/22.05/24/
  44.1/48 kHz inputs with duration held to within a millisecond.

Text is also flattened before synthesis: `!!!`, ellipses, dashes and SHOUTED
WORDS all make TTS engines speed up and raise pitch. Real abbreviations (RD,
TAC, EMS, LAPD, BOLO) are preserved. The system prompt now explicitly forbids
exclamation marks and capitals, since a real RTO reads a homicide in the same
flat tone as a parking complaint.

### Vehicle alarms no longer read the car model as the location

In-game security firm notifications look like:

```
Security Firm: vehicle alarm was set off on Tavros closest street: Alta Street
```

The parser took the text after "set off on" as the location, so it broadcast
"location Tavros", a motorcycle.

There is now a gazetteer of roughly 400 GTA V vehicle models. The parser
identifies the model and reports it as the vehicle, prefers the
`closest street:` value for the location, rejects any location candidate that is
a known vehicle model, and prefers candidates that match a real street or
district.

Vehicle alarms are now enabled by default, since they work correctly.

### New: the Brain, it knows what to flag and what not to

The flagger finds candidates; the brain decides whether a candidate is a real
incident worth radio traffic. Previously anything matching a keyword was read
aloud, so the dispatcher solemnly broadcast OOC chatter, hang-ups, prank calls,
"what time does the station open", and the same robbery four times.

It scores weapons, violence, medical, fire, in-progress wording, property crime,
collisions and whether a location was given, then subtracts for out-of-character
chatter, tests and cancellations, information requests, hang-ups and routine
complaints. Bare acknowledgements, keysmash and duplicates within a two-minute
window are rejected outright.

Fully offline and deterministic: no tokens, no added latency. Tunable via
`brain.threshold`, with `brain.log_decisions` to see exactly why anything was
suppressed. Unit traffic always bypasses it, because your `scope` settings
already decided whether you want to hear it.

### New: GTA V streets, districts and typo correction

A gazetteer of 242 streets, 85 districts and 46 landmarks across Los Santos and
Blaine County, plus the numbered highways. Caller locations are corrected before
anything is spoken:

| Caller typed | Dispatcher says |
|---|---|
| Little Soeul | Little Seoul |
| Vinwood Blvd | Vinewood Boulevard |
| Innocense Blvd | Innocence Boulevard |
| Sandy Shorez | Sandy Shores |
| Paleto Bey | Paleto Bay |
| Del Pero | Del Perro |

Abbreviations are expanded (Blvd to Boulevard) and intersections formatted (Alta
and Spanish becomes Alta Street and Spanish Avenue). It deliberately refuses to
guess: nonsense, a house, or a vehicle model does not match a street, so the app
falls back to "refer to CAD for location" instead of inventing somewhere.
Lookups are indexed and LRU-cached, and `rapidfuzz` is used when installed for
roughly a 10x speedup.

### New: RDs on every 911 call

Real LAPD broadcasts close with the incident number and reporting district
("...Incident 171 in RD 193"). Every call-out with a location now does too:

> All units, a 302 burglary at Power Street. ... Incident four one two two.
> R D, oh one forty six. Code 2. Units to handle, identify.

Always the letters "R D", never the words "reporting district". Always exactly
four digits, spoken in two-and-two pairs: 1313 becomes "thirteen thirteen", 4051
becomes "forty fifty one", 2010 becomes "twenty ten", 0105 becomes "oh one oh
five". RDs are invented but stable, so the same location always gets the same RD
across restarts, and `Grove St` matches `Grove Street`. The first two digits
derive from the district's division, so nearby streets get related RDs.

### Improved dispatch realism

Based on research into how LAPD RTOs actually talk on the air:

- The LAPD double-call is **kept**, because it is correct. Real RTOs say the
  address twice for clarity over a noisy radio ("at Grove Street, Grove
  Street"), exactly as they repeat a unit's call sign ("1 Adam 12, 1 Adam 12").
  It is now controlled by `llm.repeat_location`, which defaults to `true`. Set
  it to `false` only if you prefer the address stated once.
- Incident number and RD now close the broadcast, in that order, matching real
  LAPD format.
- The dispatcher no longer identifies itself. An RTO addresses the unit and then
  talks; the operator is never named on the air.
- Tactical channels are requested through Control ("refer to TAC-1").
- Delivery is explicitly flat and identical on every call.

### Redesigned interface

A dispatch-console look, rebuilt around a single theme definition so both modes
are consistent everywhere. Light mode is a clean high-contrast day watch; dark
mode is a proper CAD terminal, near-black navy with amber accents for live radio
traffic and green/red status lamps. New semantic colours distinguish priority
(Code 3), routine (Code 2) and brain-suppressed entries at a glance.

### The Update button now installs a re-released build

`Check for updates` reported "You are up to date" and did nothing whenever the
published release carried the same version number as the installed build.

The check was a strict greater-than comparison: `1.6.0` is not newer than
`1.6.0`, so a rebuilt and re-uploaded v1.6.0 release was refused. Anyone already
on 1.6.0 was permanently locked out of every fix published under that tag.

Version equality is now treated as installable:

- Pressing **Check for updates** manually always offers the newest published
  build, even at the same version, and says so: "You already have 1.6.0. This
  will reinstall the latest published build of it."
- The quiet check on startup follows the new `updates.allow_reinstall` setting.
  Leave it `true` to be told about rebuilds, or set it `false` to be notified
  only about genuinely higher version numbers while the manual button still
  forces a reinstall.
- If a release has no installer attached, the app now says so and points at the
  release page instead of reporting success and changing nothing.

### code six now separates backup from an additional unit

The brain treated every code six as routine. `code6` is on the list of types
that bypass scoring, and that bypass hardcoded the priority to false, so no code
six could ever raise the alert tone.

Worse, "requesting backup" sat in the same pattern that diverts a transmission
away from the code-six parser. A unit going code six and asking for backup lost
the code six entirely and was re-read as ordinary radio traffic.

Now:

- **Backup** - also help, assistance, a cover unit, expedite - is an emergency.
  It is broadcast Code 3 and raises the alert tone: "All units, one Adam twelve
  is requesting backup at Grove Street. Code 3, units responding, identify."
- **An additional unit**, a supervisor or an air unit stays routine and is
  broadcast Code 2.
- Emergencies mentioned in passing are picked up from the body of the
  transmission, not just from an explicit request. "Code six on Adam's Apple,
  I've got a body on the ground" escalates to Code 3 on its own. The same
  applies to man down, unresponsive, not breathing, no pulse, DOA, GSW, gunshot,
  bleeding, stabbed, hostage, overdose, a weapon drawn and a fight in progress.

### K9 and spelled-out call signs

Canine call signs were not recognised in any form. `K9 one`, `K9 1`, `K9-1`,
`K9 CH4`, `canine 1` and supervisor signs such as `R30K9` all failed to match,
so a canine unit could not use `scope: own` at all.

All of those now parse, and every spelling of one unit resolves to the same
unit, so `K9 one`, `K9-1` and `Canine 1` are interchangeable.

Spelled-out call signs were recognised but read aloud wrong. Because the speech
builder walked the sign one character at a time, `25 Tom 15` came out as
"twenty-five Tom Ocean Mary fifteen" and `2 Adam 55` as "two Adam David Adam
Mary fifty-five". Whole words are now kept intact, so `25 Tom 15` and `25T15`
are both read "twenty-five Tom fifteen". NATO spellings are folded onto the LAPD
word for the same letter, so `2 Alpha 55` is read "two Adam fifty-five", and a
canine unit is read "K nine", never "King nine".

### Rewritten in-app tutorial

The built-in Tutorial page was seven short cards. It is now a twelve step
walkthrough covering installation, chat-log capture, choosing a voice provider,
creating an ElevenLabs key with the Text to Speech permission, Smart Dispatch
keys, call signs including canine and spelled-out forms, flagging scope, code
six backup versus additional, alerts, streets and RDs, going live, and presets
and updating.

### Security

An ElevenLabs API key and a Discord webhook URL were committed in `config.yaml`.
Both have been cleared, and both settings now read from environment variables
(`ELEVENLABS_API_KEY`, `DISPATCH_RELAY_WEBHOOK`) so keys no longer end up in a
shared config or a zip. If you used the previous build, rotate both credentials;
anyone with that archive has them.

### Documentation

`README.md` fully rewritten as a step-by-step tutorial: install, chat log setup,
ffmpeg, and all four voice providers; how to obtain keys from ElevenLabs, Groq,
OpenAI and a local model; the exact ElevenLabs key scopes (Text to Speech = has
access, everything else off) and why the wrong scopes caused the voice to change;
a full explanation of how Smart Dispatch works, its two engines and how to turn
it on and verify it; the new brain, geo and RD features; a complete config
reference; troubleshooting; and a performance tuning section.

## 1.5.7

### Criminal points are no longer the subject's age

A code ten on a subject with 52 criminal points read out "18 criminal points".
The profile header is a two column layout: every label is rendered first
("Age:", "Criminal Points:"), then every value (18, 52). The app walked forward
from the "Criminal Points" label to the next value node, which is the age.
Labels and values are now paired by position instead, and the value inside a
badge wins, which is where the points total actually lives. As a backstop, a
points total identical to the parsed age is never reported.

The subject's age is now parsed as its own field rather than being discarded.

### MDC numbers are spoken as numbers

"52" came out as "five two" in a radio voice. Numbers in an MDC return are now
spelled out as words - "fifty-two criminal points on record", "twelve
felonies". Call signs and license plates are untouched and still go out digit by
digit, because that is correct for those.


### "to my location" is properly dead this time

1.5.7 fixed the radio path, but OPG requests are built by a different function
that never went through the scrub, so "start me an OPG tow to my location" still
came back as "en route to my location". Fixing builders one at a time is
whack-a-mole, so now **every** dispatch line leaves through a single choke point
and gets scrubbed there. A new builder cannot reintroduce this bug.

Also, "my location" is no longer treated as a place name at all: dispatch falls
back to "on the way to your location" instead of repeating the unit's phrasing.

### MDC returns sound like a dispatcher now

The return used to be one frozen sentence stitched with semicolons. Each part of
the readback now has its own pool of realistic phrasings, joined as sentences:

> "Twenty-five Tom fifteen, Connor Myer comes back clear, no wants or warrants
> on file. Be advised, subject is flagged Conceal Carry Holder. No prior arrests
> on file. Use caution."

Counts are spoken as words ("two felonies and one misdemeanor"), and safety
information still comes before paperwork.

### Executed warrants are no longer read as active

An MDC profile has two warrant tables: `tableWarrantRecord` (the page labels it
"Arrest Warrants") and `tableWarrantRecordOld` for executed ones. The app was
never fetching the second, and any warrant row looked current. Now the two are
counted separately, a row whose status says executed/served/expired/recalled is
treated as history, and the subject is only called 10-99 when the ACTIVE count
is one or more. The AI is told the same thing explicitly, so it cannot upgrade a
dead warrant either.

> "Nicky Munoz, no active warrants; MDC shows one previously executed."

### Check for updates actually works

The version parser took the first number it found in a release title - and this
app is called **911** Dispatch Relay, so every release parsed as "version 911".
Nothing could ever look newer. It now requires a dotted version and takes the
highest one in the title, so "911 Dispatch Relay v1.5.5 - v1.5.6" resolves to
1.5.6. Releases with an odd tag fall back to the release name.

For the in-app update button to install rather than just point at the page, the
release needs `911DispatchRelay-Setup-<version>.exe` attached as an asset.

### Removed: AI verification of borderline flags

That switch existed when the app read the screen with OCR and had to guess
whether text was a real call. Reading the chat log directly makes it dead
weight, and it cost an extra API round trip per flag. Gone from the settings,
the config and the code.

### Dispatch no longer repeats your own words back at you

Ask for "an OPG tow to my location" and dispatch used to answer "...en route to
my location". Dispatch speaks to you, so first person now flips to second
person: "to your location", "you need", "your twenty". This applies to the
offline wording and to the AI reply, which is also told the rule.

### "own" scope now means own

With no call signs configured, 1.5.5 treated every unit as yours so the app
could not sit silent. If you deliberately set `scope: own`, that looked like a
filter doing nothing. New switch, Settings > Only answer my call signs
(`flagging.require_callsigns`): turn it on and an empty call sign list flags
nothing at all. Left off, behaviour is unchanged.

### Old chat is no longer re-read

Two causes. A slow poll or a re-rendered chat box broke the overlap match, so
every line on screen looked new; and each re-attach truncated the session file
and wrote the whole visible window again. The capture now remembers the lines
it has already written (across reconnects) and never writes one twice, so
nothing from ten minutes ago gets answered a second time.

### MDC: the record was never actually being read

Every record table on an MDC profile is a serverSide DataTable. The profile page
we download contains column headers and nothing else, which is why a subject
with felonies and misdemeanors came back "no criminal history". The app now
requests the rows from `/record/populate/<Name>` and counts them properly.

- Caution codes lead the readback. "Conceal Carry Holder" is said before warrant
  counts, not dropped.
- If the rows cannot be read, dispatch says the criminal history could not be
  confirmed. It will never call a subject clean off the back of an empty page.

### Security firm vehicle alarms (optional)

Off by default. Settings > Flag security firm vehicle alarms
(`flagging.alarms.vehicle`) picks up vehicle alarms posted in chat by a security
firm, pulls out the model and the last known location, and puts out a call:
"All units, be advised, vehicle alarm activation on a Sultan, last seen ...".

## 1.5.6

- **Only radio traffic is flagged now.** A PM to yourself saying "25T15, clear."
  was being answered as if it went out over the air. Detectors read the raw text
  and never checked which channel it came from, so PMs, OOC, /me, /do and local
  speech could all set dispatch off. Every line is now matched to its channel -
  in the live capture format and the log file format - and anything on an ignored
  channel is dropped before a single detector runs.
- Channels to ignore are editable in Settings (PMs, OOC, /me, /do, local, whisper,
  shout, low, megaphone and phone by default). A channel that is not on the list is
  still read, so an unfamiliar channel name can never silence the app.
- "Connor Myer says [radio]: ..." is recognised as radio even without the
  [S: 1 | CH: BASE] prefix.

## 1.5.5

**Fixed: the app could look alive but never answer anything.**

- With no call signs set in Settings, every "own" flag - clearing, code six, CAD
  updates, code seven, OPG, end of watch, out status - was quietly dropped, so
  nothing was ever read out. Blank now means "answer every unit", and the log
  says so on Start. Fill in Settings > Your call signs to answer only yours.
- Live capture: FiveM's debug socket allows one client at a time, so a 500 on
  connect now says plainly that another chat tool (usually the GTAW Log Parser)
  is attached, instead of showing a raw error.
- Live capture: stale chat targets no longer abort the attach - every candidate
  is tried before giving up.
- Live capture: closing FiveM used to raise "Runtime.evaluate failed:" and
  "Page.getFrameTree failed:". Shutting the game down is now recognised as what
  it is and logged once as "FiveM closed."
- No more blank error messages, and capture status no longer triggers the
  automatic bug reporter.
- New **Clear Log** button beside Show Chat: empties the chat view and starts the
  session log fresh.

### FiveM support (also in 1.5.5)

**GTA World moved to FiveM, so the chat input moved with it.**

- FiveM does not save the chat to disk at all - it lives in the game's local NUI
  page. The app now reads the plain text session file written by the GTA World
  Chat Log Assistant (GTAW Log Parser):
  `%LOCALAPPDATA%\GTAW-Log-Parser-FiveM\current-session.txt`.
- Auto-detect looks for that file first and falls back to a RAGE MP `.storage`
  file, so old setups keep working. `input_source.source` forces one or the
  other (`auto` | `fivem` | `ragemp`).
- The reader now picks the format per file: JSON `.storage` or plain text.
- The assistant empties its session file every time FiveM starts a new session.
  The watcher detects the shrink and resyncs, instead of either replaying the
  whole backlog or going silent for the rest of the session.
- `tools/simulate_chat.py --fivem` writes a fake session file so the whole
  pipeline can be tested without being in game. `--live` targets the real path.

## v1.5.4

- Offline testing: `tools/test_flag.py` now reads your call signs the same way the app does (they were always blank before), takes `--config PATH` / `--config appdata`, prints which config file it loaded, explains why a line was not flagged, and can speak the reply out loud with `--speak`. `tools/test_mdc.py` gained `--speak` too.
- The update check now finds releases the way the PatrolOne client does: if `releases/latest` returns nothing it reads the full release list, skips drafts, and falls back to a pre-release when that is all the repository has. Rate limiting, a private repository and a wrong repository name now each report what actually happened.
- MDC name lookups no longer read out every caution code that exists. Caution flags are only taken from the subject's own caution-code badges, picker and legend markup is ignored, and anything that does not look like a flag is dropped.
- Criminal points are only read from a field actually labelled criminal points, so `Age: 21` is never spoken as "21 criminal points" again.
- Settings sections are collapsible and build their fields only while open, which makes the page open faster and easier to navigate. Added Expand all / Collapse all, and search now expands matching sections automatically.
- Offline testing: `tools/test_flag.py --all` now recognises code ten and plate requests, `tools/simulate_chat.py --say "..."` sends your own radio line to the running app, and the new `tools/test_mdc.py` reads a saved MDC page and prints exactly what dispatch would say.
- New colour language across the app, and settings search no longer redraws the page on every keystroke.

## v1.5.3

- Code six acknowledgements no longer read the rest of the transmission back as the location. A location stops at the end of the sentence, at the point the sentence stops describing a place, and after eight words.
- A code six that also asks for additionals is now answered with the request put on the air instead of "Advise if you need anything".
- Short status calls such as "25T15, clear." and "25T15, out to MRS." are no longer swallowed by the duplicate filter, or by a near-identical call from another unit. They use their own exact-match window, `flagging.status_dedup_sec`, default 90 seconds.
- Alarm flagging ignores traffic that closes an alarm ("last property alarm gonna be code four adam, no signs of any suspect") and no longer broadcasts an alarm with no location when a unit is the one speaking.
- The update check names the repository it looked at when no release has been published yet.

## v1.5.2

- MDC login no longer dies on a missing browser engine. The app now uses Microsoft Edge or Google Chrome automatically when either is installed, falls back to the bundled Chromium, keeps any downloaded engine in your app-data folder, and shows a plain-English fix instead of a raw Playwright error.
- Name and plate lookup phrases are never blank again: the built-in defaults are restored automatically whenever those boxes are empty, so code ten and plate checks work out of the box.
- New: OPG (Official Police Garage) requests are flagged and acknowledged - "roll me OPG to Route 68", "OPG flatbed", "requesting a tow truck". Optional, with its own scope setting.
- New: end of watch traffic is flagged and acknowledged, showing the unit off duty. Optional.
- New: property alarm activations (silent, audible, burglary, commercial, residential, fire, hold-up) are flagged and put out as a call.
- New: "out to <place>" (en route, unavailable) and "out at <place>" (unavailable on location) are recognised and acknowledged. Optional.
- Station abbreviations such as MRS, PHMC and PAB are now spoken in full so the voice does not read them as words.
- MDC replies no longer slip ten-codes past the filter. The spoken forms ("ten twenty-nine", "ten twenty-eight") were not recognised, only the digit forms were, and unknown codes were deleted mid-sentence instead of being translated. "Code ten" for a records check is correct LAPD usage and is left alone.
- Fixed the update check: it pointed at the wrong repository name and every check quietly returned "no releases published yet". A GitHub repository link or owner/repo is now accepted as well as a full API URL.
- New optional setting: check for updates when the app starts. If a newer version is found, a window opens with the release notes and an update button that installs it and restarts the app.
- Removed the OCR-era ignore patterns ("you are not connected", "for emergencies", "911 sign" and friends). They existed to filter game signage read off the screen, which cannot happen now the app reads the chat log.

## [1.5.1] - 2026-07-27

### Fixed
- **Asking about another unit no longer counts as clearing.** "25T20, any available canine?" was
  acknowledged as "clear and available for calls", because the word "available" anywhere in a line
  was enough to mean going available. A question mark, or a request aimed at another unit ("any",
  "anyone", "any units", "do we have", "is there", "requesting", "looking for", "can I get",
  "which unit"), now rules a clear out unless the unit explicitly reports itself clear ("show me
  clear", "I'm clear", "clear from the station", "mark us in service").
- "available" on its own is no longer treated as clearing at all. It has to be a self-report -
  "I'm available", "back available", "available for calls" - or paired with show/mark/put.
- "clearing the area" and "clearing that intersection" are no longer read as going available. Only
  "clear the..." was excluded before, so the "-ing" form slipped through.
- **Ordinary dispatch lines stopped being posted to the bug webhook as errors.** The error detector
  matched plain substrings, and the street name "Exceptionalist" contains "exception", so normal
  DISPATCH and FLAGGED lines were sent as auto-detected errors. Detection is whole-word now, and
  spoken dispatch, flag and MDC output lines are never treated as errors.

## [1.5.0] - 2026-07-27

### Added
- **Updating from inside the app.** About now shows the version you are running, checks for a newer
  release, and when one exists shows an "Update to x.y.z and restart" button. It downloads the
  installer with a progress bar, installs it silently, and the app reopens on its own. Your settings
  in `%APPDATA%` are kept.
- The check also runs quietly a couple of seconds after the app opens. It stays silent when you are
  already up to date and only speaks up when there is something to install.
- Two kinds of update source are understood. A GitHub releases API URL works directly and the
  Setup .exe attached to the release is what gets installed. Any other URL should return JSON with
  `version`, `url`, `notes` and optionally `sha256`.
- If a `sha256` is published the download is verified against it and discarded if it does not match.
  Only a `.exe` installer is ever accepted or run.
- New `updates` section in `config.yaml`: `enabled`, `check_on_start`, `manifest_url`,
  `allow_prerelease` and `timeout`.

### Changed
- The installer now closes a running copy of the app before replacing its files, which is what lets
  the in-app update work without asking you anything.
- Run from source rather than installed, the update button downloads the installer and tells you
  where it is instead of trying to replace files that are not there.

## [1.4.3] - 2026-07-27

### Changed
- **Dispatch never uses ten-codes.** The LAPD does not use them, so the dispatcher says "roger",
  "copy", "clear and available", "arrived", "stand by" and "disregard" instead of 10-4, 10-8,
  10-97 and the rest. The rule is now stated in the AI prompts (including both MDC prompts), and
  anything on its way to the voice is checked as well, so a ten-code cannot be spoken even if the
  AI writes one.
- Response codes (Code 3, Code 6, Code 4, Code 7) and bare penal-code numbers such as 211 or 415
  are correct LAPD usage and are untouched. House numbers and incident numbers are safe too:
  "104 Elgin Avenue" and "incident 26-448120" are left exactly as they are.
- Ten-code phrases a player says on the radio are still recognised as input, including "code ten"
  and "10-28" for MDC lookups. Only what dispatch speaks changed.

## [1.4.2] - 2026-07-27

Fixes for the first installed (Setup.exe) build.

### Fixed
- **Settings kept in `%APPDATA%` are now repaired on startup.** An installed build keeps your
  settings in `%APPDATA%\911 Dispatch Relay\config.yaml` so upgrades never overwrite them, but
  that also meant any setting the file did not contain silently fell back to a built-in default.
  Missing keys are now refilled from the settings shipped with the app and the repaired file is
  written back. Values you actually chose are left alone.
  This single cause produced both problems reported on a fresh install: the chat log dropping to
  polling mode, and bug reporting claiming it was not configured.
- **Bug reporting no longer dead-ends.** If direct sending is unavailable, the report is written to
  `%APPDATA%\911 Dispatch Relay\bug_reports` and the app names the exact file to send, instead of
  only saying it isn't configured. Reports are still stripped of keys and secrets first.
- The polling-mode message now names the setting responsible, and a missing or blank value for that
  setting counts as ON, which is the intended default.

## [1.4.1] - 2026-07-27

### Fixed
- **The Enable MDC button never appeared.** The MDC section was still flagged as disabled in the
  settings schema, so the whole section was replaced by a "Temporarily disabled in this release"
  notice before any of its controls were drawn. The notice and the disabled mechanism are gone.
- **Shots fired now gets a proper call-out.** "2W64, shots fired, shots fired!" is announced LAPD
  style - "All units, all units. Shots fired, shots fired. Two William sixty-four at Forum Drive.
  All units in the vicinity, respond Code 3..." - and is spoken, because it counts as priority.
- Locations given without "at" or "on" are recognised in radio traffic, so "shots fired, Forum
  Drive" no longer says "refer to CAD". With no location at all it says "refer to CAD for location".
- Punctuation from the game no longer leaks into speech ("at Elgin Avenue!").
- Short urgent traffic such as "2W64, 11-99, 11-99!" was discarded by the noise filter for being
  mostly digits. Urgent traffic now bypasses that filter.

### Changed
- Refreshed the interface colours: deeper page contrast, softer surfaces and an indigo accent in
  both light and dark themes.

## [1.4.0] - 2026-07-27

### Input: rebuilt
- The app now reads the RAGE MP chat log file (`.storage`) directly instead of capturing and
  reading your screen. Text is exact: no misread call signs, no false matches on in-world
  signage or posters, no fuzzy matching.
- `modules/file_watcher.py` finds the file automatically, tails it through the game's
  whole-file rewrites, survives the write lock, and parses radio, local, OOC, PM, HQ,
  dispatch, action and emergency-call traffic into clean message objects.
- Emergency call cards are assembled into a single event, so a call is read once and in full.
- Screen capture, OCR and region calibration are gone: `capture.py`, `ocr.py` and
  `region_selector.py` were deleted, along with Tesseract, `pytesseract`, `mss` and
  `pyautogui`. `watchdog` is now required - run `py -m pip install -r requirements.txt`.
- `tools/simulate_chat.py` drives the whole pipeline with no game, no server and no
  connection, and can replay your own saved chat log with `--from-file`.

### Fixed
- **Panic alarms were ignored.** The detector required the words "panic button", but GTA World
  writes "panic alarm" (`[LSSD PANIC ALARM] ... activated their panic alarm at ...`). Sheriff
  and parenthesised call signs such as `(283H)` are now read too.
- **Code six locations given without "on" or "at".** "25T15, code six, forum drive." now reports
  Forum Drive instead of falling back to "refer to CAD". Street types and San Andreas
  neighbourhoods are recognised, while vehicle and plate details are not mistaken for a place.
- A missing word boundary made the location pattern match the "on" inside words, so
  "code six, mission row" reported the location as "row".

### Changed
- **MDC lookups work again and are configurable.** They are driven by the chat log, so a code
  ten or a plate request is read exactly as typed. Enable them from Settings > MDC Lookup with
  the Enable MDC button, which warns you to use it at your own risk and asks for confirmation.
- **Area call-outs removed.** Without screen capture the app cannot know where your unit is, so
  guessing an area from radio chatter was dropped. Call signs remain and still drive every
  "own" setting and the phonetic read-back.
- The alert tone can now be any audio file, chosen in Settings > Alert tone.
- Settings, Dashboard and the tutorial were reorganised around the chat-log input.
