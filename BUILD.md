# Building 911 Dispatch Relay into a real installable app

This turns the Python project into a standalone Windows application (`911 Dispatch Relay.exe`)
and, optionally, a proper **Setup.exe** installer with Start Menu + desktop shortcuts and an
uninstaller. End users won't need Python or `pip` at all.

> **You must build on Windows.** PyInstaller and Inno Setup produce Windows binaries and cannot
> be cross-compiled from macOS/Linux. Build on the same kind of Windows machine you'll run on
> (64-bit).

---

## 1. Prerequisites (one time)

1. **Python 3.10-3.13** (64-bit) from https://www.python.org/downloads/ - during install tick
   *"Add python.exe to PATH"*.
   - Note: PyInstaller may lag the very newest Python. If a fresh Python 3.14 gives you trouble,
     use Python 3.12 or 3.13 for building.
2. **Inno Setup 6 or 7** (optional, only if you want the `Setup.exe`): https://jrsoftware.org/isdl.php
   - Inno Setup 7 (released July 2026) works fine - it's fully backward compatible with the
     included `installer.iss`. The 64-bit edition is recommended.
3. That's it. `build.bat` installs everything else (PyInstaller + the app's own dependencies)
   into a throwaway `.buildenv` folder so your system stays clean.

---

## 2. Build it (the easy way)

From the project folder, just double-click **`build.bat`** (or run it in a terminal).

It will:
1. create an isolated build environment (`.buildenv\`),
2. install the dependencies + PyInstaller,
3. bundle everything into `dist\911 Dispatch Relay\`,
4. if Inno Setup is installed, produce `installer_output\911DispatchRelay-Setup-1.0.0.exe`.

**Outputs:**
- **Standalone app:** `dist\911 Dispatch Relay\911 Dispatch Relay.exe` - copy this whole folder
  anywhere and run the `.exe`. No install needed.
- **Installer:** `installer_output\911DispatchRelay-Setup-1.0.0.exe` - hand this single file to
  anyone; it installs to Program Files with shortcuts + an uninstaller.

---

## 3. Build it (manual, if you prefer)

```bat
py -m venv .buildenv
.buildenv\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install pyinstaller
pyinstaller --noconfirm --clean "911DispatchRelay.spec"
```

Then, for the installer, open `installer.iss` in Inno Setup and click **Build > Compile**
(or run `ISCC.exe installer.iss`).

---

## 4. External tools: ffmpeg

- **ffmpeg** is handled automatically - it's bundled via the `imageio-ffmpeg` dependency, so the
  built app decodes audio without a separate ffmpeg install.
- **Nothing else is required.** Since v1.3.0 the app reads the RAGE MP `.storage` chat log
  directly, so there is no OCR engine to install or bundle - Tesseract, the `vendor\tesseract\`
  folder, and the `pytesseract` / `mss` / `pyautogui` dependencies are all gone.

---

## 5. Where settings live in the installed app

When run as an installed app, Program Files is read-only, so your live settings are stored in a
writable per-user file:

```
%APPDATA%\911 Dispatch Relay\config.yaml
```

It's seeded once from the bundled defaults on first launch, then edited in-app via **Settings**
(or by hand). This means your API key, voice, and chat log path survive app updates.
Running from source (plain `py main.py`) still uses the project's own `config.yaml` as before.

---

## 6. Regenerating the app icon (optional)

The icon lives at `assets\app.ico` and is already included. To tweak it:

```bat
python tools\generate_icon.py
```

---

## 7. Notes & gotchas

- **Antivirus / SmartScreen:** unsigned PyInstaller apps sometimes trigger a Windows SmartScreen
  "unknown publisher" prompt or an antivirus false positive. That's normal for unsigned software.
  To remove it, sign `911 Dispatch Relay.exe` and the installer with a code-signing certificate
  (`signtool sign /fd sha256 /a ...`). Not required for personal use.
- **First launch is slow:** one-folder PyInstaller apps unpack on start; subsequent launches are
  faster.
- **Build on the oldest Windows you must support.** Binaries built on Windows 11 generally run on
  Windows 10; the reverse isn't guaranteed.
- **Bump the version** by editing `#define AppVersion` in `installer.iss` (and the filename it
  produces) for each release.
