# Changelog

> **Version history was reset at 1.4.0.** The app was rebuilt from the ground up around a
> completely new input system, and every entry before 1.4.0 described a version that no longer
> exists - different modules, different config, different dependencies. Keeping those notes would
> only be misleading, so they have been removed entirely. 1.4.0 is the first release of the
> rebuilt app.

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
