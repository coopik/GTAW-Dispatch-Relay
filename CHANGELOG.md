# Changelog

> **Version history was reset at 1.4.0.** The app was rebuilt from the ground up around a
> completely new input system, and every entry before 1.4.0 described a version that no longer
> exists - different modules, different config, different dependencies. Keeping those notes would
> only be misleading, so they have been removed entirely. 1.4.0 is the first release of the
> rebuilt app.

## [1.4.1] - 2026-07-27

### Fixed
- **The Enable MDC button never appeared.** The MDC section was still marked as disabled in the
  settings schema, so the whole section was replaced by a "Temporarily disabled in this release"
  notice before any of its controls were drawn. The notice and the disabled mechanism are gone.
- **Shots fired now gets a proper call-out.** A broadcast such as "2W64, shots fired, shots
  fired!" is announced LAPD style - "All units, all units. Shots fired, shots fired. Two William
  sixty-four at Forum Drive. All units in the vicinity, respond Code 3..." - and is spoken over
  TTS with the alert tone, because it counts as priority traffic.
- Locations given without "at" or "on" are picked up for radio traffic too, so "shots fired,
  Forum Drive" no longer says "refer to CAD". When no location is given at all, the call-out
  says "refer to CAD for location".
- Punctuation from the game no longer leaks into speech ("at Elgin Avenue!").
- Very short urgent traffic such as "2W64, 11-99, 11-99!" was being thrown away by the noise
  filter for being mostly digits. Urgent traffic now bypasses that filter.

### Changed
- Bug reporting: a report can be saved to a file, copied to the clipboard, or the folder opened,
  in addition to sending it to the developer. Reports include the version, OS, whether it is an
  installed build, the resolved chat log path, the voice provider and the recent log.
- Bug reports are written to `%APPDATA%\911 Dispatch Relay\bug_reports`, so they keep working
  when the app is installed to Program Files, where the install folder is read-only.
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
