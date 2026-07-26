# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build spec for 911 Dispatch Relay.
# Build with:  pyinstaller --noconfirm --clean 911DispatchRelay.spec
# (build.bat does this for you.)
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Packages that ship data files / dynamic libs PyInstaller can't always find.
for pkg in ("customtkinter", "sounddevice", "soundfile", "imageio_ffmpeg",
            "edge_tts", "aiohttp", "certifi", "pystray"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

try:
    hiddenimports += collect_submodules("scipy")
except Exception:
    pass

hiddenimports += [
    "PIL", "PIL._tkinter_finder", "yaml", "numpy", "pydub", "requests",
    "watchdog", "watchdog.observers", "watchdog.observers.polling", "watchdog.events",
    # Default free voice (edge-tts) + its async HTTP deps, so it works out of the box:
    "edge_tts", "aiohttp", "certifi", "pyttsx3", "keyboard",
    # Optional minimize-to-tray support:
    "pystray", "pystray._win32",
    # pywin32 (Windows "Select Window" mode) + DPAPI session encryption for MDC:
    "win32gui", "win32ui", "win32con", "win32api", "pywintypes", "pythoncom", "win32crypt",
    # Optional MDC Lookup Assistant HTML parsing:
    "bs4", "soupsieve",
]

# Optional MDC Lookup Assistant. beautifulsoup4 is bundled; Playwright is NOT
# fully bundled (its Chromium browser is downloaded separately via
# "py -m playwright install chromium"), but include its Python package if present
# so the interactive login import works when run from source or a full install.
for pkg in ("bs4", "playwright"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# App data files bundled read-only next to the exe.
datas += [("config.yaml", "."), ("assets", "assets")]


block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="911 Dispatch Relay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowed GUI app (no console window)
    disable_windowed_traceback=False,
    icon=os.path.join("assets", "app.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="911 Dispatch Relay",
)
