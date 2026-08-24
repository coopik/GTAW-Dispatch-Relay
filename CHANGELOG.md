# Changelog

> **Version history was reset at 1.4.0.** The app was rebuilt from the ground up around a
> completely new input system, and every entry before 1.4.0 described a version that no longer
> exists - different modules, different config, different dependencies. Keeping those notes would
> only be misleading, so they have been removed entirely. 1.4.0 is the first release of the
> rebuilt app.

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
