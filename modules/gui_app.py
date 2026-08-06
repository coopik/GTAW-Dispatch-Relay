from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from collections import deque

import customtkinter as ctk

try:
    import yaml
except Exception:
    yaml = None

try:
    from modules import icons
except Exception:
    icons = None

try:
    from modules import usage
except Exception:
    usage = None

APP_VERSION = "1.5.2"

PALETTE = {
    "page": ("#f1f4f9", "#080d17"),
    "sidebar": ("#ffffff", "#0c1322"),
    "card": ("#ffffff", "#0f1829"),
    "card_alt": ("#f5f7fb", "#16223a"),
    "border": ("#e4e9f2", "#22304d"),
    "text": ("#0b1220", "#eaeef6"),
    "muted": ("#6b7a90", "#94a3b8"),
    "primary": ("#4f46e5", "#6366f1"),
    "primary_hover": ("#4338ca", "#4f46e5"),
    "start": ("#0f9d58", "#22c55e"),
    "start_hover": ("#0c7c46", "#16a34a"),
    "stop": ("#dc2626", "#ef4444"),
    "stop_hover": ("#b91c1c", "#dc2626"),
    "neutral": ("#eceff5", "#1b2740"),
    "neutral_hover": ("#dfe4ee", "#2a3a5c"),
    "idle": ("#94a3b8", "#64748b"),
    "live": ("#0f9d58", "#22c55e"),
    "speak": ("#ea580c", "#fb923c"),
}

IC_DARK = "#334155"
IC_DARK_ON = "#cbd5e1"
IC_PRIMARY = "#4f46e5"
IC_PRIMARY_ON = "#818cf8"
IC_WHITE = "#ffffff"


def _get(cfg, path, default=None):
    cur = cfg
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return default if cur is None else cur


def _set(cfg, path, value):
    cur = cfg
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value


_KEYSYM_MAP = {
    "Return": "enter", "Escape": "esc", "space": "space", "Tab": "tab",
    "BackSpace": "backspace", "Delete": "delete", "Prior": "page up",
    "Next": "page down", "Home": "home", "End": "end", "Up": "up",
    "Down": "down", "Left": "left", "Right": "right", "Insert": "insert",
    "Control_L": "ctrl", "Control_R": "ctrl", "Alt_L": "alt", "Alt_R": "alt",
    "Shift_L": "shift", "Shift_R": "shift",
}


def _normalize_key(keysym):
    if not keysym:
        return ""
    if keysym in _KEYSYM_MAP:
        return _KEYSYM_MAP[keysym]
    return keysym.lower()


SETTINGS_SCHEMA = [
    ("Chat log input", "scan", [
        {"kind": "action_input", "label": "Chat log file"},
        {"path": ["input_source", "path"], "label": "File path", "kind": "text",
         "hint": r"Full path to the RAGE MP .storage file, e.g. "
                 r"C:\RAGEMP\client_resources\<hash>\.storage  "
                 "Leave blank to auto-detect it."},
        {"path": ["input_source", "auto_detect"], "label": "Auto-detect the file on start", "kind": "bool",
         "hint": "Searches your RAGE MP install for the GTA World .storage file. "
                 "A path set above always wins."},
        {"path": ["input_source", "use_watchdog"], "label": "Instant file notifications", "kind": "bool",
         "hint": "Reacts the moment the game writes the file. Turn off to use plain "
                 "polling only (slightly slower, but bulletproof)."},
        {"path": ["input_source", "poll_interval"], "label": "Poll interval (seconds)", "kind": "float",
         "hint": "Safety-net re-check of the file. 0.75 is a good default."},
        {"path": ["input_source", "debounce_ms"], "label": "Settle delay (ms)", "kind": "int",
         "hint": "How long to wait after a file change before reading, so a half-written "
                 "file is never parsed. 250 is safe."},
        {"path": ["input_source", "retry_attempts"], "label": "Read retries", "kind": "int",
         "hint": "The game client holds the file open while it rewrites it. Each read is "
                 "retried this many times before being skipped."},
        {"path": ["ui", "open_monitor"], "label": "Open app window on", "kind": "monitor",
         "hint": "Which display the app window opens on. Applies now and on every launch."},
    ], "The app reads the chat log file GTA World writes on your own PC, so it sees the "
       "exact text of every message - correct call signs, no misreads, and nothing from "
       "in-world signs or menus. Nothing is ever written back to the file or to the game."),
    ("Voice (TTS)", "mic", [
        {"path": ["tts", "provider"], "label": "Provider", "kind": "choice",
         "choices": ["elevenlabs", "edge", "pyttsx3", "google"]},
        {"path": ["tts", "speak_digits"], "label": "Speak numbers digit-by-digit", "kind": "bool"},
        {"path": ["tts", "elevenlabs", "api_key"], "label": "ElevenLabs API key", "kind": "secret"},
        {"path": ["tts", "elevenlabs", "voice_id"], "label": "ElevenLabs voice ID", "kind": "text"},
        {"path": ["tts", "elevenlabs", "model_id"], "label": "ElevenLabs model", "kind": "text"},
        {"path": ["tts", "elevenlabs", "stability"], "label": "Stability", "kind": "slider",
         "from": 0.0, "to": 1.0},
        {"path": ["tts", "elevenlabs", "similarity_boost"], "label": "Similarity boost", "kind": "slider",
         "from": 0.0, "to": 1.0},
    ], None),
    ("Dispatch AI", "chip", [
        {"path": ["llm", "enabled"], "label": "Enable AI rewrite", "kind": "bool"},
        {"path": ["llm", "emergency_only"], "label": "Emergencies only (skip landline/non-emergency)",
         "kind": "bool"},
        {"path": ["llm", "tac_referral"], "label": "Refer priority calls to TAC (pursuits, shots fired)",
         "kind": "bool"},
        {"path": ["llm", "verify_flags"], "label": "AI verification: double-check borderline flags before dispatch (needs API key)",
         "kind": "bool"},
        {"path": ["llm", "provider"], "label": "Provider", "kind": "text"},
        {"path": ["llm", "base_url"], "label": "Base URL", "kind": "text"},
        {"path": ["llm", "model"], "label": "Model", "kind": "text"},
        {"path": ["llm", "api_key"], "label": "API key (blank = offline generator)", "kind": "secret"},
        {"path": ["llm", "timeout"], "label": "Timeout (seconds)", "kind": "int"},
    ], None),
    ("Flagging", "flag", [
        {"path": ["flagging", "min_body_length"], "label": "Minimum message length", "kind": "int"},
        {"path": ["flagging", "fuzzy_threshold"], "label": "Duplicate strictness", "kind": "slider",
         "from": 0.5, "to": 1.0},
        {"path": ["flagging", "dedup_history"], "label": "De-dup memory (lines)", "kind": "int"},
        {"path": ["flagging", "call_block", "enabled"], "label": "Parse MDC / 911 call cards", "kind": "bool"},
        {"path": ["flagging", "radio_traffic"], "label": "Read unit radio traffic (base channel)", "kind": "bool"},
        {"path": ["flagging", "skip_own_names"], "label": "Skip your own characters", "kind": "list",
         "hint": "Comma-separated character names, e.g. Connor Myer. When the AI sees \"<name> "
                 "says:\" in chat or radio, that line is ignored - so requesting an additional "
                 "unit yourself won't trigger a call-out. It'll help preserve tokens if you're "
                 "using a custom AI API."},
        {"path": ["flagging", "panic_button"], "label": "React to panic-button alerts", "kind": "bool",
         "hint": "When an in-game panic button is activated, put out an urgent Code 3 "
                 "officer-in-distress call-out."},
        {"path": ["flagging", "cad_updates", "enabled"], "label": "Acknowledge CAD update requests", "kind": "bool",
         "hint": "Reply to \"<call sign>, Dispatch, update my CAD location/status\" over the radio."},
        {"path": ["flagging", "cad_updates", "scope"], "label": "CAD updates apply to", "kind": "choice",
         "choices": ["own", "all"],
         "hint": "\"own\" answers only your own call signs (from Your call signs); "
                 "\"all\" answers any unit's CAD update request."},
        {"path": ["flagging", "code_six", "enabled"], "label": "Acknowledge code six / stop requests", "kind": "bool",
         "hint": "Reply when a unit marks code six, e.g. \"<call sign>, mark me code six\", "
                 "\"show me code six\", or \"<call sign>, I'm code six on Elgin Avenue\"."},
        {"path": ["flagging", "code_six", "scope"], "label": "Code six applies to", "kind": "choice",
         "choices": ["own", "all"],
         "hint": "\"own\" answers only your own call signs (from Your call signs); "
                 "\"all\" answers any unit going code six."},
        {"path": ["flagging", "code_six", "detail"], "label": "Code six detail", "kind": "choice",
         "choices": ["detailed", "simple"],
         "hint": "\"detailed\" reads back the vehicle and license plate (spelled phonetically) on "
                 "traffic stops; \"simple\" gives only the call sign and location."},
        {"path": ["flagging", "code_seven", "enabled"], "label": "Acknowledge code seven (out of service / meal)", "kind": "bool",
         "hint": "Reply when a unit goes code seven, e.g. \"<call sign>, show me code seven\" or "
                 "\"<call sign>, code seven at Pershing Square\"."},
        {"path": ["flagging", "code_seven", "scope"], "label": "Code seven applies to", "kind": "choice",
         "choices": ["own", "all"],
         "hint": "\"own\" answers only your own call signs; \"all\" answers any unit going code seven."},
        {"path": ["flagging", "clear_ack", "enabled"], "label": "Acknowledge clear / back in service", "kind": "bool",
         "hint": "Reply when a unit clears, e.g. \"<call sign>, show me clear\", \"<call sign>, clear\", "
                 "or \"<call sign>, show me available\"."},
        {"path": ["flagging", "clear_ack", "scope"], "label": "Clear applies to", "kind": "choice",
         "choices": ["own", "all"],
         "hint": "\"own\" answers only your own call signs; \"all\" answers any unit clearing."},
        {"path": ["flagging", "opg", "enabled"], "label": "Acknowledge OPG (police garage) requests", "kind": "bool",
         "hint": "Reply when a unit asks for the Official Police Garage, e.g. \"roll me OPG to Route 68\" "
                 "or \"requesting an OPG flatbed\". Handles flatbed, tow truck and transport requests."},
        {"path": ["flagging", "opg", "scope"], "label": "OPG requests apply to", "kind": "choice",
         "choices": ["own", "all"],
         "hint": "\"own\" answers only your own call signs; \"all\" answers any unit requesting OPG."},
        {"path": ["flagging", "end_of_watch", "enabled"], "label": "Acknowledge end of watch", "kind": "bool",
         "hint": "Reply when a unit calls end of watch / EOW / signing off, and show them off duty."},
        {"path": ["flagging", "end_of_watch", "scope"], "label": "End of watch applies to", "kind": "choice",
         "choices": ["own", "all"],
         "hint": "\"own\" answers only your own call signs; \"all\" answers any unit going end of watch."},
        {"path": ["flagging", "out_status", "enabled"], "label": "Acknowledge out to / out at", "kind": "bool",
         "hint": "\"<call sign>, out to MRS\" = en route and unavailable; \"<call sign>, out at MRS\" = "
                 "unavailable at that location. Station abbreviations are spoken in full."},
        {"path": ["flagging", "out_status", "scope"], "label": "Out to / out at applies to", "kind": "choice",
         "choices": ["own", "all"],
         "hint": "\"own\" answers only your own call signs; \"all\" answers any unit going out to or out at."},
        {"path": ["flagging", "alarms", "enabled"], "label": "Flag property alarms", "kind": "bool",
         "hint": "Put out a call when a property alarm activation comes over the radio - silent, audible, "
                 "burglary, commercial or residential."},
    ], None),
    ("MDC Lookup (optional)", "search", [
        {"kind": "action_mdc", "label": "Web MDC session"},
        {"kind": "action_mdc_toggle", "label": "Enable MDC lookups"},
        {"path": ["mdc_lookup", "scope"], "label": "Lookups apply to", "kind": "choice",
         "choices": ["own", "all"],
         "hint": "\"own\" reacts only when one of your own call signs asks for the run; "
                 "\"all\" reacts to any unit's request."},
        {"path": ["mdc_lookup", "cooldown_sec"], "label": "Cooldown between lookups (sec)", "kind": "int",
         "hint": "Minimum seconds between requests to the Web MDC. Do not lower this recklessly."},
        {"path": ["mdc_lookup", "response_channel"], "label": "Response channel label", "kind": "text",
         "hint": "Optional text spoken before each result, e.g. \"TAC 2\". Leave blank for none."},
        {"path": ["mdc_lookup", "name_patterns"], "label": "Name lookup phrases", "kind": "lines",
         "hint": "One regular expression per line. Each must contain a (?P<target>...) group. "
                 "Matched case-insensitively."},
        {"path": ["mdc_lookup", "plate_patterns"], "label": "Plate lookup phrases", "kind": "lines",
         "hint": "One regular expression per line. Each must contain a (?P<plate>...) group. "
                 "Matched case-insensitively."},
    ], "OPTIONAL and OFF by default. Reads a \u201crun this name / plate\u201d request straight out of the game "
       "chat log and looks it up in GTA World's Web MDC (https://mdc.gta.world/), then reads the "
       "result back over the radio. READ-ONLY. \u26a0 Automating a logged-in site may violate GTA World's "
       "rules - use only on your own account, at your own risk. You log in yourself in a real browser "
       "window; your password is never seen or stored, only the session (encrypted with Windows DPAPI). ",
     False),
    ("Your call signs", "shield", [
        {"path": ["location", "callsigns"], "label": "Your call signs", "kind": "list",
         "hint": "Comma-separated, e.g. 2XL13, 2Adam55. Spoken with the police phonetic alphabet."},
    ], "Tells the app which units are yours. Everything set to \u201cown\u201d - CAD updates, code six, "
       "code seven, clearing and MDC lookups - only answers these call signs, and they are read "
       "back using the police phonetic alphabet."),
    ("Global hotkeys", "target", [
        {"path": ["hotkeys", "enabled"], "label": "Enable global hotkeys", "kind": "bool"},
        {"path": ["hotkeys", "start"], "label": "Start key", "kind": "hotkey"},
        {"path": ["hotkeys", "stop"], "label": "Stop key", "kind": "hotkey"},
    ], "Optional. Bind keys that Start / Stop the relay from anywhere - even while GTA is "
       "focused. Click Record, then press a key (e.g. F9). Needs the 'keyboard' package: "
       "pip install keyboard."),
    ("Radio effect", "radio", [
        {"path": ["radiofx", "intensity"], "label": "Intensity", "kind": "slider", "from": 0.0, "to": 1.0},
        {"path": ["radiofx", "bandpass_low_hz"], "label": "Low cut (Hz)", "kind": "int"},
        {"path": ["radiofx", "bandpass_high_hz"], "label": "High cut (Hz)", "kind": "int"},
        {"path": ["radiofx", "noise_level"], "label": "Static level", "kind": "float"},
        {"path": ["radiofx", "distortion"], "label": "Distortion", "kind": "slider", "from": 0.0, "to": 1.0},
        {"path": ["radiofx", "key_click"], "label": "Mic key click", "kind": "bool"},
    ], None),
    ("Playback", "volume", [
        {"path": ["playback", "volume"], "label": "Volume", "kind": "slider", "from": 0.0, "to": 1.0},
        {"path": ["playback", "max_queue"], "label": "Max queued calls", "kind": "int"},
    ], None),
    ("Alert tone", "bell", [
        {"path": ["alert", "enabled"], "label": "Play alert before dispatch", "kind": "bool"},
        {"path": ["alert", "scope"], "label": "Play alert for", "kind": "choice",
         "choices": ["all", "priorities"],
         "hint": "\"all\" plays the alert before every call-out; \"priorities\" only before "
                 "urgent Code 3 / officer-in-distress calls."},
        {"path": ["alert", "volume"], "label": "Alert volume", "kind": "slider", "from": 0.0, "to": 1.0},
        {"path": ["alert", "gap_ms"], "label": "Gap after alert (ms)", "kind": "int"},
        {"path": ["alert", "path"], "label": "Alert tone file", "kind": "file",
         "filetypes": [("Audio", ".wav .mp3 .ogg .flac"), ("All files", "*.*")],
         "hint": "Any .wav / .mp3 / .ogg file. Leave blank for the bundled tone. Restart or press "
                 "Save to load the new file."},
    ], None),
    ("Debug & diagnostics", "search", [
        {"path": ["ui", "debug"], "label": "Debug mode (show full activity log in Report a bug console)", "kind": "bool",
         "hint": "When on, the console on the \"Report a bug\" tab streams every log line like a "
                 "terminal. When off, it only shows errors and warnings."},
        {"path": ["reporting", "report_system_errors"], "label": "Auto-send app errors to the developer", "kind": "bool",
         "hint": "When the app hits an error, quietly send a redacted, rate-limited report over the "
                 "developer's Discord webhook so it can be fixed. No API keys or secrets are ever sent."},
        {"path": ["ui", "minimize_to_tray"], "label": "Minimize to system tray (instead of taskbar)", "kind": "bool",
         "hint": "When on, clicking minimize hides the window to the system tray. Right-click the tray "
                 "icon to restore or quit. If the tray package isn't available it falls back to the taskbar."},
        {"path": ["updates", "check_on_start"], "label": "Check for updates when the app starts", "kind": "bool",
         "hint": "A few seconds after launch the app asks GitHub whether a newer version exists. "
                 "If there is one, a window opens with the release notes and an update button. "
                 "Nothing is downloaded or installed until you click it."},
        {"path": ["updates", "enabled"], "label": "Allow update checks", "kind": "bool",
         "hint": "Turn this off to stop the app contacting GitHub at all. The Check for updates "
                 "button on the About page stops working too."},
    ], None),
]


class DispatchApp(ctk.CTk):
    def __init__(self, relay, save_config):
        super().__init__()
        self.relay = relay
        self.save_config = save_config
        self._log_lines: deque = deque(maxlen=300)
        self._recent_sig = None
        self._preview_on = False
        self._getters = []
        self._nav_icons = {}
        self._nav_labels = {}
        self._sidebar_collapsed = bool(_get(relay.cfg, ["ui", "sidebar_collapsed"], False))
        self._current_page = "dashboard"
        self._tray_icon = None
        self._last_open_monitor = None
        self._last_debug = None

        theme = str(_get(relay.cfg, ["ui", "theme"], "light")).lower()
        if theme not in ("light", "dark"):
            theme = "light"
        ctk.set_appearance_mode(theme)
        self.title(f"911 Dispatch Relay  v{APP_VERSION}")
        self.geometry("1060x730")
        self.minsize(960, 640)
        self.configure(fg_color=PALETTE["page"])

        self.f_title = ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        self.f_h = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        self.f_b = ctk.CTkFont(family="Segoe UI", size=13)
        self.f_bb = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.f_s = ctk.CTkFont(family="Segoe UI", size=11)
        self.f_mono = ctk.CTkFont(family="Consolas", size=12)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._container = ctk.CTkFrame(self, fg_color="transparent")
        self._container.grid(row=0, column=1, sticky="nsew")
        self._container.grid_rowconfigure(0, weight=1)
        self._container.grid_columnconfigure(0, weight=1)

        self._pages = {}
        self._pages["dashboard"] = self._build_dashboard()
        self._pages["tutorial"] = self._build_tutorial()
        self._pages["settings"] = self._build_settings()
        self._pages["bugs"] = self._build_bugs()
        self._pages["about"] = self._build_about()

        self.relay.set_log_callback(self._log_lines.append)
        self._apply_sidebar_state()
        self._show("dashboard")
        self._refresh_target()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Unmap>", self._on_unmap)
        self.after(300, self._tick)
        self.after(160, lambda: self._apply_open_monitor(force=True))

    def _icon(self, name, size=18, color=IC_DARK):
        if icons is None:
            return None
        dark = {IC_DARK: IC_DARK_ON, IC_PRIMARY: IC_PRIMARY_ON,
                IC_WHITE: IC_WHITE}.get(color, color)
        try:
            return icons.get_ctk_image(name, size, color, dark)
        except Exception:
            try:
                return icons.get_ctk_image(name, size, color)
            except Exception:
                return None

    def _card(self, parent):
        return ctk.CTkFrame(parent, corner_radius=14, fg_color=PALETTE["card"],
                            border_width=1, border_color=PALETTE["border"])

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, width=228, corner_radius=0, fg_color=PALETTE["sidebar"],
                           border_width=0)
        bar.grid(row=0, column=0, sticky="nsew")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(8, weight=1)
        bar.grid_columnconfigure(0, weight=1)
        self._sidebar = bar

        self._collapse_btn = ctk.CTkButton(
            bar, text="\u00ab", width=34, height=30, corner_radius=8, font=self.f_bb,
            fg_color=PALETTE["card_alt"], text_color=PALETTE["text"],
            hover_color=PALETTE["primary_hover"], command=self._toggle_sidebar)
        self._collapse_btn.grid(row=0, column=0, padx=14, pady=(14, 2), sticky="e")

        self._side_logo = ctk.CTkLabel(bar, text="", image=self._icon("siren", 46, IC_PRIMARY),
                                       anchor="center")
        self._side_logo.grid(row=1, column=0, pady=(8, 4), padx=22, sticky="ew")
        self._side_title = ctk.CTkLabel(bar, text="Dispatch Relay", font=self.f_title,
                                        text_color=PALETTE["text"], anchor="center")
        self._side_title.grid(row=2, column=0, padx=12, sticky="ew")
        self._side_subtitle = ctk.CTkLabel(bar, text="GTA World \u2022 local only", font=self.f_s,
                                           text_color=PALETTE["muted"], anchor="center")
        self._side_subtitle.grid(row=3, column=0, padx=12, sticky="ew", pady=(0, 18))

        self._nav_btns = {}
        for i, (key, label, icon) in enumerate([
            ("dashboard", "Dashboard", "dashboard"),
            ("tutorial", "Tutorial", "book"),
            ("settings", "Settings", "settings"),
            ("bugs", "Report a bug", "flag"),
            ("about", "About", "info"),
        ]):
            self._nav_labels[key] = label
            self._nav_icons[key] = (self._icon(icon, 18, IC_DARK), self._icon(icon, 18, IC_WHITE))
            b = ctk.CTkButton(
                bar, text=f"  {label}", anchor="w", height=44, corner_radius=10,
                font=self.f_bb, fg_color="transparent", text_color=PALETTE["text"],
                hover_color=PALETTE["card_alt"], image=self._nav_icons[key][0], compound="left",
                command=lambda k=key: self._show(k))
            b.grid(row=4 + i, column=0, padx=14, pady=3, sticky="ew")
            self._nav_btns[key] = b

        self._side_status = ctk.CTkLabel(bar, text="\u25cb  Idle", font=self.f_bb,
                                         text_color=PALETTE["idle"])
        self._side_status.grid(row=9, column=0, padx=22, pady=(0, 6), sticky="w")
        self._side_queue = ctk.CTkLabel(bar, text="queue: 0", font=self.f_s,
                                        text_color=PALETTE["muted"])
        self._side_queue.grid(row=10, column=0, padx=22, pady=(0, 22), sticky="w")

    def _toggle_sidebar(self):
        self._sidebar_collapsed = not self._sidebar_collapsed
        self._apply_sidebar_state()
        try:
            _set(self.relay.cfg, ["ui", "sidebar_collapsed"], self._sidebar_collapsed)
            self.save_config(self.relay.cfg, self.relay.config_path)
        except Exception:
            pass

    def _apply_sidebar_state(self):
        collapsed = self._sidebar_collapsed
        try:
            self._sidebar.configure(width=66 if collapsed else 228)
        except Exception:
            pass
        if collapsed:
            self._side_title.grid_remove()
            self._side_subtitle.grid_remove()
            self._side_queue.grid_remove()
        else:
            self._side_title.grid()
            self._side_subtitle.grid()
            self._side_queue.grid()
        for key, b in self._nav_btns.items():
            if collapsed:
                b.configure(text="", anchor="center", compound="top")
            else:
                b.configure(text=f"  {self._nav_labels[key]}", anchor="w", compound="left")
        self._collapse_btn.configure(text="\u00bb" if collapsed else "\u00ab")
        # Only re-highlight the nav button here; do NOT touch the page area, or
        self._highlight_nav(self._current_page)

    def _show(self, key):
        self._current_page = key
        for k, page in self._pages.items():
            if k == key:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_remove()
        self._highlight_nav(key)

    def _highlight_nav(self, key):
        for k, b in self._nav_btns.items():
            active = k == key
            dark, white = self._nav_icons.get(k, (None, None))
            b.configure(fg_color=PALETTE["primary"] if active else "transparent",
                        text_color="#ffffff" if active else PALETTE["text"],
                        hover_color=PALETTE["primary_hover"] if active else PALETTE["card_alt"],
                        image=white if active else dark)

    def _build_dashboard(self):
        page = ctk.CTkScrollableFrame(self._container, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 8))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="Dashboard", font=self.f_title,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w")
        self._build_theme_toggle(head).grid(row=0, column=1, sticky="e")

        sc = self._card(page)
        sc.grid(row=1, column=0, sticky="ew", padx=26, pady=8)
        sc.grid_columnconfigure(1, weight=1)
        self._status_dot = ctk.CTkLabel(sc, text="\u25cf", font=ctk.CTkFont(size=30),
                                        text_color=PALETTE["idle"])
        self._status_dot.grid(row=0, column=0, rowspan=2, padx=(22, 10), pady=18)
        self._status_text = ctk.CTkLabel(sc, text="Idle", font=self.f_title,
                                         text_color=PALETTE["text"])
        self._status_text.grid(row=0, column=1, sticky="w", pady=(18, 0))
        self._status_sub = ctk.CTkLabel(sc, text="Not watching", font=self.f_b,
                                        text_color=PALETTE["muted"])
        self._status_sub.grid(row=1, column=1, sticky="w", pady=(0, 18))

        self._start_btn = ctk.CTkButton(sc, text="  Start", width=124, height=46,
                                        corner_radius=12, font=self.f_h,
                                        fg_color=PALETTE["start"], hover_color=PALETTE["start_hover"],
                                        image=self._icon("play", 18, IC_WHITE), compound="left",
                                        command=self._do_start)
        self._start_btn.grid(row=0, column=2, rowspan=2, padx=(10, 8), pady=18)
        self._stop_btn = ctk.CTkButton(sc, text="  Stop", width=124, height=46,
                                       corner_radius=12, font=self.f_h,
                                       fg_color=PALETTE["stop"], hover_color=PALETTE["stop_hover"],
                                       image=self._icon("stop", 18, IC_WHITE), compound="left",
                                       command=self.relay.stop)
        self._stop_btn.grid(row=0, column=3, rowspan=2, padx=(0, 22), pady=18)

        self._build_credits_card(page, 2)

        cc = self._card(page)
        cc.grid(row=3, column=0, sticky="ew", padx=26, pady=8)
        cc.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cc, text="Chat log input", font=self.f_h,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w", padx=22, pady=(16, 2))
        ctk.CTkLabel(cc, text="Reads the .storage file your RAGE MP client writes the game chat to.",
                     font=self.f_s, text_color=PALETTE["muted"]).grid(
            row=1, column=0, sticky="w", padx=22, pady=(0, 6))
        self._target_lbl = ctk.CTkLabel(cc, text="", font=self.f_mono,
                                        text_color=PALETTE["muted"], anchor="w",
                                        justify="left", wraplength=620)
        self._target_lbl.grid(row=2, column=0, sticky="w", padx=22, pady=(0, 8))

        row = ctk.CTkFrame(cc, fg_color="transparent")
        row.grid(row=3, column=0, sticky="w", padx=18, pady=(0, 8))
        ctk.CTkButton(row, text="  Detect file", width=150, height=40,
                      corner_radius=10, font=self.f_bb, fg_color=PALETTE["primary"],
                      hover_color=PALETTE["primary_hover"],
                      image=self._icon("target", 16, IC_WHITE), compound="left",
                      command=self._do_detect).grid(row=0, column=0, padx=4)
        ctk.CTkButton(row, text="  Browse...", width=130, height=40, corner_radius=10,
                      font=self.f_bb, fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"], image=self._icon("search", 16, IC_DARK),
                      compound="left", command=self._do_browse).grid(row=0, column=1, padx=4)
        ctk.CTkButton(row, text="  Test Voice", width=140, height=40, corner_radius=10,
                      font=self.f_bb, fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"], image=self._icon("mic", 16, IC_DARK),
                      compound="left", command=self._do_test).grid(row=0, column=2, padx=4)
        self._preview_btn = ctk.CTkButton(row, text="  Show Chat", width=140, height=40,
                                          corner_radius=10, font=self.f_bb, fg_color=PALETTE["neutral"],
                                          text_color=PALETTE["text"], hover_color=PALETTE["neutral_hover"],
                                          image=self._icon("scan", 16, IC_DARK), compound="left",
                                          command=self._toggle_preview)
        self._preview_btn.grid(row=0, column=3, padx=4)
        self._preview_box = ctk.CTkTextbox(cc, height=150, font=self.f_mono, corner_radius=10,
                                          fg_color=PALETTE["card_alt"], text_color=PALETTE["text"],
                                          border_width=0, wrap="none")
        self._preview_box.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 16))
        self._make_readonly(self._preview_box)
        self._preview_box.grid_remove()

        rechead = ctk.CTkFrame(page, fg_color="transparent")
        rechead.grid(row=4, column=0, sticky="ew", padx=30, pady=(10, 2))
        rechead.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(rechead, text="Recent calls", font=self.f_h,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(rechead, text="Clear", width=70, height=28, corner_radius=8, font=self.f_s,
                      fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"],
                      command=self._clear_recent).grid(row=0, column=1, sticky="e")
        self._recent_frame = ctk.CTkScrollableFrame(page, height=220, fg_color=PALETTE["card"],
                                                    corner_radius=14, border_width=1,
                                                    border_color=PALETTE["border"])
        self._recent_frame.grid(row=5, column=0, sticky="ew", padx=26, pady=4)
        self._recent_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self._recent_frame, text="No calls yet.", font=self.f_b,
                     text_color=PALETTE["muted"]).grid(row=0, column=0, sticky="w", padx=14, pady=14)

        loghead = ctk.CTkFrame(page, fg_color="transparent")
        loghead.grid(row=6, column=0, sticky="ew", padx=30, pady=(12, 2))
        loghead.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(loghead, text="Activity log", font=self.f_h,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(loghead, text="Clear", width=70, height=28, corner_radius=8, font=self.f_s,
                      fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"],
                      command=self._log_lines.clear).grid(row=0, column=1, sticky="e")
        self._log_box = ctk.CTkTextbox(page, height=150, font=self.f_mono, corner_radius=14,
                                       fg_color="#0f172a", text_color="#8ef0a6", border_width=0,
                                       wrap="word")
        self._log_box.grid(row=7, column=0, sticky="ew", padx=26, pady=(4, 20))
        self._make_readonly(self._log_box)
        return page

    def _build_settings(self):
        page = ctk.CTkFrame(self._container, fg_color="transparent")
        page.grid_rowconfigure(3, weight=1)
        page.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 6))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="Settings", font=self.f_title,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w")
        self._save_hint = ctk.CTkLabel(head, text="", font=self.f_b, text_color=PALETTE["start"])
        self._save_hint.grid(row=0, column=1, padx=10)
        ctk.CTkButton(head, text="  Reload", width=100, height=38, corner_radius=10, font=self.f_bb,
                      fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"], image=self._icon("reload", 16, IC_DARK),
                      compound="left", command=self._reload_settings).grid(row=0, column=2, padx=(0, 6))
        ctk.CTkButton(head, text="  Save", width=120, height=38, corner_radius=10,
                      font=self.f_bb, fg_color=PALETTE["primary"], hover_color=PALETTE["primary_hover"],
                      image=self._icon("save", 16, IC_WHITE), compound="left",
                      command=self._save_settings).grid(row=0, column=3)

        self._build_preset_bar(page)
        self._build_search_bar(page)

        body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        body.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 16))
        body.grid_columnconfigure(0, weight=1)
        self._settings_body = body
        self._render_settings()
        return page

    def _render_settings(self):
        for child in self._settings_body.winfo_children():
            child.destroy()
        self._getters = []
        self._input_status_lbl = None
        try:
            query = (self._search_var.get() or "").strip().lower()
        except Exception:
            query = ""
        shown = 0
        for entry in SETTINGS_SCHEMA:
            title, icon, fields = entry[0], entry[1], entry[2]
            desc = entry[3] if len(entry) > 3 else None
            disabled = entry[4] if len(entry) > 4 else False
            if query and not self._section_matches(title, fields, query):
                continue
            sec = self._card(self._settings_body)
            sec.grid(row=shown, column=0, sticky="ew", padx=12, pady=8)
            sec.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(sec, text=f"  {title}", font=self.f_h, text_color=PALETTE["text"],
                         image=self._icon(icon, 18, IC_PRIMARY), compound="left").grid(
                row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(14, 6))
            row = 1
            if desc:
                ctk.CTkLabel(sec, text=desc, font=self.f_s, text_color=PALETTE["muted"],
                             anchor="w", justify="left", wraplength=620).grid(
                    row=row, column=0, columnspan=3, sticky="w", padx=18, pady=(0, 8))
                row += 1
            for field in fields:
                row = self._add_field(sec, row, field)
            shown += 1
        if query and shown == 0:
            ctk.CTkLabel(self._settings_body, text="No settings match your search.",
                         font=self.f_b, text_color=PALETTE["muted"]).grid(
                row=0, column=0, sticky="w", padx=20, pady=20)

    def _add_field(self, parent, row, field):
        kind = field["kind"]
        label = field["label"]
        hint = field.get("hint")

        if kind == "action_input":
            ctk.CTkLabel(parent, text=label, font=self.f_b, text_color=PALETTE["text"],
                         anchor="w").grid(row=row, column=0, sticky="w", padx=(18, 12), pady=6)
            self._input_status_lbl = ctk.CTkLabel(
                parent, text=self._input_status_text(), font=self.f_s,
                text_color=PALETTE["muted"], anchor="w", justify="left", wraplength=380)
            self._input_status_lbl.grid(row=row, column=1, sticky="w", padx=12, pady=6)
            btns = ctk.CTkFrame(parent, fg_color="transparent")
            btns.grid(row=row, column=2, sticky="e", padx=(6, 18), pady=6)
            ctk.CTkButton(btns, text="  Detect", width=110, height=36, corner_radius=10,
                          font=self.f_bb, fg_color=PALETTE["primary"], hover_color=PALETTE["primary_hover"],
                          image=self._icon("target", 16, IC_WHITE), compound="left",
                          command=self._do_detect).grid(row=0, column=0, padx=4)
            ctk.CTkButton(btns, text="Browse...", width=100, height=36, corner_radius=10,
                          font=self.f_bb, fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                          hover_color=PALETTE["neutral_hover"],
                          command=self._do_browse).grid(row=0, column=1, padx=4)
            return row + 1

        if kind == "action_mdc_toggle":
            ctk.CTkLabel(parent, text=label, font=self.f_b, text_color=PALETTE["text"],
                         anchor="w").grid(row=row, column=0, sticky="w", padx=(18, 12), pady=6)
            on = bool(_get(self.relay.cfg, ["mdc_lookup", "enabled"], False))
            self._mdc_enable_lbl = ctk.CTkLabel(
                parent, text=("Enabled - use at your own risk" if on else "Disabled"),
                font=self.f_s, text_color=(PALETTE["primary"] if on else PALETTE["muted"]),
                anchor="w")
            self._mdc_enable_lbl.grid(row=row, column=1, sticky="w", padx=12, pady=6)
            ctk.CTkButton(parent, text=("Disable MDC" if on else "Enable MDC"), width=130,
                          height=36, corner_radius=10, font=self.f_bb,
                          fg_color=(PALETTE["neutral"] if on else PALETTE["primary"]),
                          text_color=(PALETTE["text"] if on else "#ffffff"),
                          hover_color=(PALETTE["neutral_hover"] if on else PALETTE["primary_hover"]),
                          command=self._do_mdc_toggle).grid(row=row, column=2, sticky="e",
                                                            padx=(6, 18), pady=6)
            return row + 1

        if kind == "action_mdc":
            ctk.CTkLabel(parent, text=label, font=self.f_b, text_color=PALETTE["text"],
                         anchor="w").grid(row=row, column=0, sticky="w", padx=(18, 12), pady=6)
            self._mdc_status_lbl = ctk.CTkLabel(
                parent, text=self._mdc_status_text(), font=self.f_s, text_color=PALETTE["muted"],
                anchor="w")
            self._mdc_status_lbl.grid(row=row, column=1, sticky="w", padx=12, pady=6)
            btns = ctk.CTkFrame(parent, fg_color="transparent")
            btns.grid(row=row, column=2, sticky="e", padx=(6, 18), pady=6)
            ctk.CTkButton(btns, text="  Log in", width=110, height=36, corner_radius=10,
                          font=self.f_bb, fg_color=PALETTE["primary"], hover_color=PALETTE["primary_hover"],
                          image=self._icon("search", 16, IC_WHITE), compound="left",
                          command=self._do_mdc_login).grid(row=0, column=0, padx=4)
            ctk.CTkButton(btns, text="Log out", width=90, height=36, corner_radius=10, font=self.f_bb,
                          fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                          hover_color=PALETTE["neutral_hover"],
                          command=self._do_mdc_logout).grid(row=0, column=1, padx=4)
            return row + 1

        path = field["path"]
        val = _get(self.relay.cfg, path)
        ctk.CTkLabel(parent, text=label, font=self.f_b, text_color=PALETTE["text"],
                     anchor="w", justify="left").grid(row=row, column=0, sticky="w",
                                                      padx=(18, 12), pady=6)
        if kind == "bool":
            var = tk.BooleanVar(value=bool(val))
            ctk.CTkSwitch(parent, text="", variable=var, onvalue=True, offvalue=False,
                          progress_color=PALETTE["primary"]).grid(
                row=row, column=1, columnspan=2, sticky="w", padx=12, pady=6)
            self._getters.append((path, lambda v=var: bool(v.get())))
        elif kind == "choice":
            var = tk.StringVar(value=str(val) if val is not None else field["choices"][0])
            ctk.CTkOptionMenu(parent, values=field["choices"], variable=var, width=220,
                              font=self.f_b, fg_color=PALETTE["card_alt"],
                              button_color=PALETTE["primary"], button_hover_color=PALETTE["primary_hover"],
                              text_color=PALETTE["text"]).grid(
                row=row, column=1, columnspan=2, sticky="w", padx=12, pady=6)
            self._getters.append((path, lambda v=var: v.get()))
        elif kind == "monitor":
            opts = self._monitor_options()
            labels = [lbl for _, lbl in opts]
            idx_to_label = {idx: lbl for idx, lbl in opts}
            label_to_idx = {lbl: idx for idx, lbl in opts}
            cur = int(val) if isinstance(val, (int, float)) else 0
            var = tk.StringVar(value=idx_to_label.get(cur, labels[0]))
            ctk.CTkOptionMenu(parent, values=labels, variable=var, width=260,
                              font=self.f_b, fg_color=PALETTE["card_alt"],
                              button_color=PALETTE["primary"], button_hover_color=PALETTE["primary_hover"],
                              text_color=PALETTE["text"]).grid(
                row=row, column=1, columnspan=2, sticky="w", padx=12, pady=6)
            self._getters.append((path, lambda v=var, m=label_to_idx: m.get(v.get(), 0)))
        elif kind == "slider":
            lo, hi = float(field.get("from", 0.0)), float(field.get("to", 1.0))
            var = tk.DoubleVar(value=float(val) if val is not None else lo)
            valuelbl = ctk.CTkLabel(parent, text=f"{var.get():.2f}", font=self.f_bb,
                                    text_color=PALETTE["primary"], width=44)
            valuelbl.grid(row=row, column=2, sticky="e", padx=(6, 18), pady=6)
            ctk.CTkSlider(parent, from_=lo, to=hi, variable=var, number_of_steps=100,
                          progress_color=PALETTE["primary"], button_color=PALETTE["primary"],
                          button_hover_color=PALETTE["primary_hover"],
                          command=lambda x, l=valuelbl: l.configure(text=f"{float(x):.2f}")).grid(
                row=row, column=1, sticky="ew", padx=12, pady=6)
            self._getters.append((path, lambda v=var: round(float(v.get()), 3)))
        elif kind == "list":
            cur = val
            if isinstance(cur, list):
                cur = ", ".join(str(x) for x in cur)
            ent = ctk.CTkEntry(parent, width=320, font=self.f_b, fg_color=PALETTE["card_alt"],
                               border_color=PALETTE["border"], text_color=PALETTE["text"])
            if cur:
                ent.insert(0, str(cur))
            ent.grid(row=row, column=1, columnspan=2, sticky="ew", padx=12, pady=6)
            self._getters.append(
                (path, lambda e=ent: [s.strip() for s in e.get().replace("\n", ",").split(",")
                                      if s.strip()]))
        elif kind == "lines":
            cur = val
            if isinstance(cur, list):
                cur = "\n".join(str(x) for x in cur)
            box = ctk.CTkTextbox(parent, width=320, height=92, font=self.f_mono,
                                 fg_color=PALETTE["card_alt"], border_width=1,
                                 border_color=PALETTE["border"], text_color=PALETTE["text"],
                                 wrap="none")
            if cur:
                box.insert("1.0", str(cur))
            box.grid(row=row, column=1, columnspan=2, sticky="ew", padx=12, pady=6)
            # One entry per line; do NOT split on commas (regex uses commas, e.g. {0,2}).
            self._getters.append(
                (path, lambda b=box: [ln.strip() for ln in b.get("1.0", "end").splitlines()
                                      if ln.strip()]))
        elif kind == "file":
            ent = ctk.CTkEntry(parent, width=320, font=self.f_b, fg_color=PALETTE["card_alt"],
                               border_color=PALETTE["border"], text_color=PALETTE["text"])
            if val:
                ent.insert(0, str(val))
            ent.grid(row=row, column=1, sticky="ew", padx=12, pady=6)
            ctk.CTkButton(parent, text="Browse...", width=100, height=34, corner_radius=10,
                          font=self.f_bb, fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                          hover_color=PALETTE["neutral_hover"],
                          command=lambda e=ent, f=field: self._do_browse_file(e, f)).grid(
                row=row, column=2, sticky="e", padx=(6, 18), pady=6)
            self._getters.append((path, lambda e=ent: e.get().strip()))
        elif kind == "hotkey":
            var = tk.StringVar(value=str(val) if val else "")
            box = ctk.CTkFrame(parent, fg_color="transparent")
            box.grid(row=row, column=1, columnspan=2, sticky="w", padx=12, pady=6)
            ctk.CTkLabel(box, textvariable=var, font=self.f_bb, text_color=PALETTE["primary"],
                         width=120, anchor="w").grid(row=0, column=0, padx=(0, 8))
            rec = ctk.CTkButton(box, text="Record", width=90, height=32, corner_radius=8,
                                font=self.f_bb, fg_color=PALETTE["primary"],
                                hover_color=PALETTE["primary_hover"])
            rec.configure(command=lambda v=var, b=rec: self._record_hotkey(v, b))
            rec.grid(row=0, column=1, padx=4)
            ctk.CTkButton(box, text="Clear", width=70, height=32, corner_radius=8, font=self.f_bb,
                          fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                          hover_color=PALETTE["neutral_hover"],
                          command=lambda v=var: v.set("")).grid(row=0, column=2, padx=4)
            self._getters.append((path, lambda v=var: v.get().strip()))
        else:
            show = "\u2022" if kind == "secret" else ""
            ent = ctk.CTkEntry(parent, width=320, font=self.f_b, show=show,
                               fg_color=PALETTE["card_alt"], border_color=PALETTE["border"],
                               text_color=PALETTE["text"])
            if val is not None:
                ent.insert(0, str(val))
            ent.grid(row=row, column=1, columnspan=2, sticky="ew", padx=12, pady=6)
            self._getters.append((path, lambda e=ent, k=kind: self._coerce(e.get(), k)))

        row += 1
        if hint:
            ctk.CTkLabel(parent, text=hint, font=self.f_s, text_color=PALETTE["muted"],
                         anchor="w", justify="left", wraplength=560).grid(
                row=row, column=1, columnspan=2, sticky="w", padx=12, pady=(0, 6))
            row += 1
        return row

    @staticmethod
    def _hud_text(region):
        return f"Current: {region}" if region else "Current: not set"

    def _monitor_options(self):
        opts = [(0, "Default (primary display)")]
        try:
            from modules import displays
            for m in displays.list_monitors():
                idx = int(m["index"])
                opts.append((idx, f"Monitor {idx}  -  {int(m['width'])}x{int(m['height'])}"))
        except Exception:
            pass
        return opts

    def _apply_open_monitor(self, force=False):
        try:
            idx = int(_get(self.relay.cfg, ["ui", "open_monitor"], 0) or 0)
        except Exception:
            idx = 0
        if not force and idx == self._last_open_monitor:
            return
        self._last_open_monitor = idx
        if idx <= 0:
            return
        try:
            from modules import displays
            mons = displays.list_monitors()
        except Exception:
            return
        if idx > len(mons):
            return
        mon = mons[idx - 1]
        try:
            self.update_idletasks()
            w = self.winfo_width() or 1060
            h = self.winfo_height() or 730
            x = int(mon["left"]) + max(0, (int(mon["width"]) - w) // 2)
            y = int(mon["top"]) + max(0, (int(mon["height"]) - h) // 3)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    @staticmethod
    def _coerce(text, kind):
        text = text.strip()
        if kind == "int":
            return int(float(text)) if text != "" else None
        if kind == "float":
            return float(text) if text != "" else None
        return text

    def _save_settings(self):
        errors = 0
        for path, getter in self._getters:
            try:
                _set(self.relay.cfg, path, getter())
            except Exception:
                errors += 1
        try:
            self.save_config(self.relay.cfg, self.relay.config_path)
            self.relay.apply_config()
        except Exception as exc:
            self._save_hint.configure(text=f"Save failed: {exc}", text_color=PALETTE["stop"])
            return
        msg = "Saved \u2713" if not errors else f"Saved with {errors} skipped"
        self._save_hint.configure(text=msg, text_color=PALETTE["start"])
        self.after(2500, lambda: self._save_hint.configure(text=""))
        self._refresh_target()
        self._apply_open_monitor()

    def _reload_settings(self):
        self._render_settings()
        self._save_hint.configure(text="Reloaded from file", text_color=PALETTE["muted"])
        self.after(2000, lambda: self._save_hint.configure(text=""))

    def _record_hotkey(self, var, btn):
        old_txt = btn.cget("text")
        btn.configure(text="Press a key...", fg_color=PALETTE["speak"])

        def _finish(event):
            key = _normalize_key(getattr(event, "keysym", ""))
            if key:
                var.set(key)
            try:
                self.unbind("<Key>", handler)
            except Exception:
                pass
            btn.configure(text=old_txt, fg_color=PALETTE["primary"])

        handler = self.bind("<Key>", _finish, add="+")

    def _presets_dir(self):
        base = os.path.dirname(os.path.abspath(self.relay.config_path))
        d = os.path.join(base, "presets")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d

    def _list_presets(self):
        try:
            return sorted(f[:-5] for f in os.listdir(self._presets_dir())
                          if f.endswith(".yaml"))
        except Exception:
            return []

    def _refresh_preset_menu(self):
        names = self._list_presets() or ["(none)"]
        try:
            self._preset_menu.configure(values=names)
            if self._preset_var.get() not in names:
                self._preset_var.set(names[0])
        except Exception:
            pass

    def _flash_hint(self, msg, ok=True):
        self._save_hint.configure(text=msg,
                                  text_color=PALETTE["start"] if ok else PALETTE["stop"])
        self.after(2600, lambda: self._save_hint.configure(text=""))

    def _gather_into_cfg(self):
        for path, getter in self._getters:
            try:
                _set(self.relay.cfg, path, getter())
            except Exception:
                pass

    def _save_preset_as(self):
        if yaml is None:
            self._flash_hint("PyYAML not available", ok=False)
            return
        try:
            dlg = ctk.CTkInputDialog(text="Name this preset:", title="Save preset")
            name = dlg.get_input()
        except Exception:
            name = None
        if not name:
            return
        name = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        if not name:
            self._flash_hint("Invalid preset name", ok=False)
            return
        self._gather_into_cfg()
        try:
            with open(os.path.join(self._presets_dir(), name + ".yaml"), "w",
                      encoding="utf-8") as f:
                yaml.safe_dump(self.relay.cfg, f, sort_keys=False, allow_unicode=True)
        except Exception as exc:
            self._flash_hint(f"Save failed: {exc}", ok=False)
            return
        self._refresh_preset_menu()
        self._preset_var.set(name)
        self._flash_hint(f"Preset '{name}' saved")

    def _load_preset(self):
        if yaml is None:
            self._flash_hint("PyYAML not available", ok=False)
            return
        name = self._preset_var.get()
        if not name or name == "(none)":
            return
        path = os.path.join(self._presets_dir(), name + ".yaml")
        if not os.path.exists(path):
            self._flash_hint("Preset not found", ok=False)
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            self._flash_hint(f"Load failed: {exc}", ok=False)
            return
        self.relay.cfg.clear()
        self.relay.cfg.update(data)
        try:
            self.save_config(self.relay.cfg, self.relay.config_path)
            self.relay.apply_config()
        except Exception as exc:
            self._flash_hint(f"Applied with error: {exc}", ok=False)
        self._render_settings()
        self._refresh_target()
        self._flash_hint(f"Preset '{name}' loaded")

    def _delete_preset(self):
        name = self._preset_var.get()
        if not name or name == "(none)":
            return
        try:
            os.remove(os.path.join(self._presets_dir(), name + ".yaml"))
        except Exception:
            pass
        self._refresh_preset_menu()
        self._flash_hint(f"Preset '{name}' deleted")

    def _build_preset_bar(self, page):
        bar = self._card(page)
        bar.grid(row=1, column=0, sticky="ew", padx=26, pady=(0, 6))
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bar, text="  Presets", font=self.f_bb, text_color=PALETTE["text"],
                     image=self._icon("save", 16, IC_PRIMARY), compound="left").grid(
            row=0, column=0, sticky="w", padx=(16, 10), pady=12)
        self._preset_var = tk.StringVar(value="")
        self._preset_menu = ctk.CTkOptionMenu(
            bar, values=self._list_presets() or ["(none)"], variable=self._preset_var,
            width=200, font=self.f_b, fg_color=PALETTE["card_alt"],
            button_color=PALETTE["primary"], button_hover_color=PALETTE["primary_hover"],
            text_color=PALETTE["text"])
        self._preset_menu.grid(row=0, column=1, sticky="w", pady=12)
        self._refresh_preset_menu()
        ctk.CTkButton(bar, text="Load", width=80, height=34, corner_radius=8, font=self.f_bb,
                      fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"], command=self._load_preset).grid(
            row=0, column=2, padx=4, pady=12)
        ctk.CTkButton(bar, text="Save as...", width=104, height=34, corner_radius=8,
                      font=self.f_bb, fg_color=PALETTE["primary"],
                      hover_color=PALETTE["primary_hover"], command=self._save_preset_as).grid(
            row=0, column=3, padx=4, pady=12)
        ctk.CTkButton(bar, text="Delete", width=80, height=34, corner_radius=8, font=self.f_bb,
                      fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"], command=self._delete_preset).grid(
            row=0, column=4, padx=(4, 16), pady=12)

    def _build_theme_toggle(self, parent):
        self._theme_mode = "dark" if str(ctk.get_appearance_mode()).lower() == "dark" else "light"
        pill = ctk.CTkFrame(parent, corner_radius=18, fg_color=PALETTE["neutral"],
                            border_width=1, border_color=PALETTE["border"])
        self._theme_buttons = {}
        for i, (key, icon, label) in enumerate(
                [("light", "sun", "Light"), ("dark", "moon", "Dark")]):
            b = ctk.CTkButton(pill, text=f"  {label}", width=86, height=32, corner_radius=15,
                              font=self.f_bb, compound="left",
                              command=lambda k=key: self._set_theme(k))
            b.grid(row=0, column=i, padx=4, pady=4)
            self._theme_buttons[key] = (b, icon)
        self._style_theme_toggle()
        return pill

    def _style_theme_toggle(self):
        for key, (btn, icon) in self._theme_buttons.items():
            active = key == self._theme_mode
            btn.configure(
                fg_color=PALETTE["primary"] if active else "transparent",
                hover_color=PALETTE["primary_hover"] if active else PALETTE["neutral_hover"],
                text_color="#ffffff" if active else PALETTE["muted"],
                image=self._icon(icon, 16, IC_WHITE if active else IC_DARK))

    def _set_theme(self, mode):
        if mode not in ("light", "dark"):
            mode = "light"
        self._theme_mode = mode
        ctk.set_appearance_mode(mode)
        self._style_theme_toggle()
        _set(self.relay.cfg, ["ui", "theme"], mode)
        try:
            self.save_config(self.relay.cfg, self.relay.config_path)
        except Exception:
            pass

    def _build_search_bar(self, page):
        bar = self._card(page)
        bar.grid(row=2, column=0, sticky="ew", padx=26, pady=(0, 6))
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bar, text="", image=self._icon("search", 16, IC_PRIMARY)).grid(
            row=0, column=0, padx=(16, 6), pady=10)
        self._search_var = tk.StringVar(value="")
        ent = ctk.CTkEntry(bar, textvariable=self._search_var, height=34, corner_radius=10,
                           font=self.f_b, fg_color=PALETTE["card_alt"],
                           border_color=PALETTE["border"], text_color=PALETTE["text"],
                           placeholder_text="Search settings...")
        ent.grid(row=0, column=1, sticky="ew", padx=6, pady=10)
        self._search_var.trace_add("write", lambda *a: self._render_settings())
        ctk.CTkButton(bar, text="Clear", width=76, height=34, corner_radius=8, font=self.f_bb,
                      fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"],
                      command=lambda: self._search_var.set("")).grid(
            row=0, column=2, padx=(6, 16), pady=10)

    @staticmethod
    def _section_matches(title, fields, query):
        if query in title.lower():
            return True
        for f in fields:
            if query in str(f.get("label", "")).lower():
                return True
            if query in str(f.get("hint", "")).lower():
                return True
        return False

    def _build_credits_card(self, page, grid_row):
        card = self._card(page)
        card.grid(row=grid_row, column=0, sticky="ew", padx=26, pady=8)
        card.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 2))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="  API credits", font=self.f_h, text_color=PALETTE["text"],
                     image=self._icon("chip", 18, IC_PRIMARY), compound="left").grid(
            row=0, column=0, sticky="w")
        ctk.CTkButton(head, text="  Refresh", width=104, height=32, corner_radius=8,
                      font=self.f_bb, fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"],
                      image=self._icon("reload", 15, IC_DARK), compound="left",
                      command=self._refresh_credits).grid(row=0, column=1, sticky="e")
        self._el_line = ctk.CTkLabel(card, text="ElevenLabs: checking...", font=self.f_bb,
                                     text_color=PALETTE["text"], anchor="w")
        self._el_line.grid(row=1, column=0, sticky="w", padx=22, pady=(6, 2))
        self._el_bar = ctk.CTkProgressBar(card, height=10, corner_radius=6,
                                          progress_color=PALETTE["primary"])
        self._el_bar.set(0)
        self._el_bar.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 4))
        self._el_sub = ctk.CTkLabel(card, text="", font=self.f_s, text_color=PALETTE["muted"],
                                    anchor="w")
        self._el_sub.grid(row=3, column=0, sticky="w", padx=22, pady=(0, 6))
        self._llm_line = ctk.CTkLabel(card, text="Dispatch AI: checking...", font=self.f_bb,
                                      text_color=PALETTE["text"], anchor="w")
        self._llm_line.grid(row=4, column=0, sticky="w", padx=22, pady=(2, 16))
        self.after(1200, self._refresh_credits)

    def _refresh_credits(self):
        try:
            self._el_line.configure(text="ElevenLabs: checking...")
            self._llm_line.configure(text="Dispatch AI: checking...")
        except Exception:
            return
        threading.Thread(target=self._credits_worker, daemon=True).start()

    def _credits_worker(self):
        cfg = self.relay.cfg
        el = {"ok": False, "error": "unavailable"}
        llm = {"ok": False, "error": "offline generator"}
        if usage is not None:
            try:
                provider = str(_get(cfg, ["tts", "provider"], "")).lower()
                if provider == "elevenlabs":
                    el = usage.elevenlabs_credits(_get(cfg, ["tts", "elevenlabs", "api_key"], "") or "")
                else:
                    el = {"ok": False, "error": "ElevenLabs not selected"}
            except Exception as exc:
                el = {"ok": False, "error": str(exc)}
            try:
                if _get(cfg, ["llm", "enabled"], False) and _get(cfg, ["llm", "api_key"], ""):
                    llm = usage.openai_credits(
                        _get(cfg, ["llm", "base_url"], "") or "",
                        _get(cfg, ["llm", "api_key"], "") or "")
            except Exception as exc:
                llm = {"ok": False, "error": str(exc)}
        self.after(0, lambda: self._apply_credits(el, llm))

    def _apply_credits(self, el, llm):
        try:
            if el.get("ok"):
                used = float(el.get("used", 0) or 0)
                limit = float(el.get("limit", 0) or 0)
                remaining = el.get("remaining")
                if remaining is None:
                    remaining = max(0.0, limit - used)
                frac = (used / limit) if limit else 0.0
                self._el_line.configure(text=f"ElevenLabs: {int(remaining):,} characters left")
                self._el_bar.set(max(0.0, min(1.0, 1.0 - frac)))
                tier = el.get("tier")
                self._el_sub.configure(
                    text=f"{int(used):,} / {int(limit):,} used"
                         + (f"   -   {tier} plan" if tier else ""))
            else:
                self._el_line.configure(text=f"ElevenLabs: {el.get('error', 'unavailable')}")
                self._el_bar.set(0)
                self._el_sub.configure(text="")
            if llm.get("ok"):
                rem = llm.get("remaining")
                unit = llm.get("unit", "")
                self._llm_line.configure(text=f"Dispatch AI: {rem} {unit} remaining")
            else:
                self._llm_line.configure(
                    text=f"Dispatch AI: connected ({llm.get('error', 'unavailable')})"
                    if _get(self.relay.cfg, ["llm", "api_key"], "") else
                    "Dispatch AI: offline generator (no API key)")
        except Exception:
            pass

    def _build_tutorial(self):
        page = ctk.CTkScrollableFrame(self._container, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(page, text="Tutorial", font=self.f_title,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w",
                                                       padx=26, pady=(22, 4))
        ctk.CTkLabel(page, text="How to use 911 Dispatch Relay, step by step.",
                     font=self.f_b, text_color=PALETTE["muted"]).grid(
            row=1, column=0, sticky="w", padx=26, pady=(0, 8))
        steps = [
            ("target", "1. Point it at your chat log",
             "Go to the Dashboard and press Detect file. The app finds the .storage file your "
             "RAGE MP client writes the game chat to (usually "
             r"C:\RAGEMP\client_resources\<hash>\.storage). If it can't find it, press "
             "Browse... and pick the file yourself. That one file is all the app ever reads."),
            ("mic", "2. Set up your voice",
             "Open Settings > Voice (TTS). Keep ElevenLabs for the best quality and paste your API "
             "key and voice ID, or switch the provider to a free offline voice. Use Test Voice on "
             "the Dashboard to hear it."),
            ("chip", "3. (Optional) Turn on Dispatch AI",
             "Settings > Dispatch AI lets an LLM rewrite calls into realistic LAPD radio traffic. "
             "Leave the API key blank to use the built-in offline generator, or add a key from "
             "OpenAI, Groq, or any OpenAI-compatible provider."),
            ("flag", "4. Choose what gets flagged",
             "Settings > Flagging controls 911 chat lines, MDC / 911 call cards, and unit radio "
             "traffic on the base channel. Tune these if too much or too little is being read."),
            ("shield", "5. Add your call signs",
             "Settings > Your call signs tells the app which units are yours, so it answers your "
             "CAD, code six, code seven and clearing traffic and reads your call sign back with "
             "the police phonetic alphabet."),
            ("play", "6. Go live",
             "Press Start on the Dashboard. The status turns green (Listening) and orange "
             "(Speaking) while audio plays. Recent calls and the activity log update live. Press "
             "Stop to pause."),
            ("save", "7. Save presets",
             "Use the Presets bar in Settings to save and reload complete configurations - handy "
             "for different servers or characters."),
        ]
        for i, (icon, title, body) in enumerate(steps):
            card = self._card(page)
            card.grid(row=2 + i, column=0, sticky="ew", padx=26, pady=6)
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=f"  {title}", font=self.f_h, text_color=PALETTE["text"],
                         image=self._icon(icon, 18, IC_PRIMARY), compound="left").grid(
                row=0, column=0, sticky="w", padx=20, pady=(14, 2))
            ctk.CTkLabel(card, text=body, font=self.f_b, text_color=PALETTE["muted"],
                         anchor="w", justify="left", wraplength=640).grid(
                row=1, column=0, sticky="w", padx=20, pady=(0, 16))
        tip = ctk.CTkFrame(page, corner_radius=14, fg_color=PALETTE["card_alt"],
                           border_width=1, border_color=PALETTE["border"])
        tip.grid(row=2 + len(steps), column=0, sticky="ew", padx=26, pady=(8, 20))
        tip.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(tip, text="  It only reads the chat log file your own game client writes, "
                     "and only ever reads it. It never touches game memory or the network, "
                     "never writes to the file, and never sends anything in-game.",
                     font=self.f_b, text_color=PALETTE["text"], anchor="w",
                     justify="left", wraplength=620,
                     image=self._icon("info", 18, IC_PRIMARY), compound="left").grid(
            row=0, column=0, sticky="w", padx=20, pady=16)
        return page

    def _build_about(self):
        page = ctk.CTkFrame(self._container, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(page, text="About", font=self.f_title,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w", padx=26, pady=(22, 8))
        card = self._card(page)
        card.grid(row=1, column=0, sticky="ew", padx=26, pady=8)
        card.grid_columnconfigure(0, weight=1)
        text = (
            "911 Dispatch Relay is a personal, local tool for GTA World roleplay.\n\n"
            "It reads the chat log your own RAGE MP client already writes to disk (the\n"
            ".storage file), detects 911 chat lines and 911 / 311 call cards, rewrites\n"
            "them into a realistic LAPD radio call-out using the San Andreas Penal Code,\n"
            "adds a radio effect, and plays the audio through your own speakers only.\n\n"
            "It can optionally track where your unit is from your own radio traffic and,\n"
            "when a call is in your area, address your unit directly using the police\n"
            "phonetic alphabet.\n\n"
            "It reads that one file READ-ONLY. It does NOT read game memory, does NOT\n"
            "touch the network or the game process, and does NOT perform any in-game\n"
            "actions or broadcasting."
        )
        ctk.CTkLabel(card, text=text, font=self.f_b, justify="left", anchor="w",
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w", padx=22, pady=20)
        upd = self._card(page)
        upd.grid(row=2, column=0, sticky="ew", padx=26, pady=8)
        upd.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(upd, text="  Version", font=self.f_h, text_color=PALETTE["text"],
                     image=self._icon("info", 18, IC_PRIMARY), compound="left").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(upd, text=f"You are running version {APP_VERSION}.", font=self.f_bb,
                     text_color=PALETTE["text"]).grid(row=1, column=0, columnspan=3,
                                                      sticky="w", padx=22)
        self._upd_status = ctk.CTkLabel(upd, text="", font=self.f_s, justify="left",
                                        anchor="w", text_color=PALETTE["muted"])
        self._upd_status.grid(row=2, column=0, columnspan=3, sticky="w", padx=22, pady=(3, 0))
        self._upd_bar = ctk.CTkProgressBar(upd, height=10, corner_radius=6,
                                           progress_color=PALETTE["primary"])
        self._upd_bar.set(0)
        self._upd_bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=22, pady=(8, 0))
        self._upd_bar.grid_remove()
        self._upd_btn = ctk.CTkButton(upd, text="  Check for updates", height=38, width=180,
                                      corner_radius=10, font=self.f_bb,
                                      fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                                      hover_color=PALETTE["neutral_hover"],
                                      image=self._icon("reload", 16, IC_DARK), compound="left",
                                      command=self._check_updates)
        self._upd_btn.grid(row=4, column=0, sticky="w", padx=(22, 8), pady=(14, 18))
        self._upd_install = ctk.CTkButton(upd, text="  Update and restart", height=38, width=210,
                                          corner_radius=10, font=self.f_bb,
                                          fg_color=PALETTE["primary"], text_color="#ffffff",
                                          hover_color=PALETTE["primary_hover"],
                                          image=self._icon("save", 16, IC_WHITE), compound="left",
                                          command=self._do_install_update)
        self._upd_install.grid(row=4, column=1, sticky="w", pady=(14, 18))
        self._upd_install.grid_remove()

        support = self._card(page)
        support.grid(row=3, column=0, sticky="ew", padx=26, pady=8)
        support.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(support, text="  Found a bug?", font=self.f_h, text_color=PALETTE["text"],
                     image=self._icon("info", 18, IC_PRIMARY), compound="left").grid(
            row=0, column=0, sticky="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(support, text="DM me on Discord:  _coopik_", font=self.f_bb,
                     text_color=PALETTE["primary"]).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 4))
        ctk.CTkLabel(support, text="Please include what you were doing and a screenshot if you can.",
                     font=self.f_s, text_color=PALETTE["muted"]).grid(row=2, column=0, sticky="w", padx=22, pady=(0, 18))

        ctk.CTkLabel(page, text=f"911 Dispatch Relay  v{APP_VERSION}    (c) 2026 COOPIK - All rights reserved.", font=self.f_bb,
                     text_color=PALETTE["text"]).grid(row=4, column=0, sticky="w", padx=30, pady=(8, 2))
        ctk.CTkLabel(page, text="Audio stays on your machine - nothing is sent in-game.",
                     font=self.f_s, text_color=PALETTE["muted"]).grid(row=5, column=0, sticky="w",
                                                                      padx=30, pady=(0, 12))
        try:
            if (_get(self.relay.cfg, ["updates", "enabled"], True)
                    and _get(self.relay.cfg, ["updates", "check_on_start"], True)
                    and not getattr(self, "_upd_started", False)):
                self._upd_started = True
                self.after(2500, lambda: self._check_updates(manual=False, popup=True))
        except Exception:
            pass
        return page

    def _updater(self):
        obj = getattr(self, "_upd_obj", None)
        if obj is None:
            try:
                from modules.updater import Updater

                obj = Updater(self.relay.cfg, APP_VERSION)
            except Exception:
                obj = False
            self._upd_obj = obj
        return obj or None

    def _upd_say(self, text, tone="muted"):
        try:
            self._upd_status.configure(text=text, text_color=PALETTE.get(tone, PALETTE["muted"]))
        except Exception:
            pass

    def _check_updates(self, manual=True, popup=False):
        up = self._updater()
        if up is None or not up.configured():
            self._upd_say("Update checks are not available on this build.")
            return
        if getattr(self, "_upd_busy", False):
            return
        self._upd_busy = True
        try:
            self._upd_btn.configure(state="disabled", text="  Checking...")
        except Exception:
            pass
        self._upd_say("Checking for updates...")
        threading.Thread(target=self._upd_check_worker, args=(up, manual, popup),
                         daemon=True).start()

    def _upd_check_worker(self, up, manual, popup=False):
        try:
            found, info, msg = up.check()
        except Exception as exc:
            found, info, msg = False, None, "Update check failed: %s" % exc
        self.after(0, lambda: self._upd_apply_check(found, info, msg, manual, popup))

    def _upd_apply_check(self, found, info, msg, manual, popup=False):
        self._upd_busy = False
        try:
            self._upd_btn.configure(state="normal", text="  Check for updates")
        except Exception:
            pass
        self._upd_found = info if found else None
        if found and info:
            note = [ln for ln in (info.notes or "").strip().splitlines() if ln.strip()]
            head = note[0][:90] if note else ""
            self._upd_say(msg + (("  " + head) if head else ""), "primary")
            try:
                self._upd_install.configure(text="  Update to %s and restart" % info.version)
                self._upd_install.grid()
            except Exception:
                pass
            if popup:
                try:
                    self._show_update_popup(info)
                except Exception as exc:
                    self._log_lines.append("Update window could not open: %s" % exc)
        else:
            try:
                self._upd_install.grid_remove()
            except Exception:
                pass
            if manual or "up to date" not in msg.lower():
                self._upd_say(msg)

    def _show_update_popup(self, info):
        if info is None:
            return
        old = getattr(self, "_upd_popup", None)
        if old is not None:
            try:
                if old.winfo_exists():
                    old.lift()
                    return
            except Exception:
                pass
        win = ctk.CTkToplevel(self)
        self._upd_popup = win
        card = PALETTE.get("card", PALETTE["page"])
        win.title("Update available")
        win.geometry("580x440")
        win.minsize(480, 360)
        win.configure(fg_color=PALETTE["page"])
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(3, weight=1)
        try:
            win.transient(self)
        except Exception:
            pass
        ctk.CTkLabel(win, text="Version %s is available" % info.version,
                     font=self.f_title, text_color=PALETTE["text"]).grid(
            row=0, column=0, sticky="w", padx=24, pady=(22, 2))
        ctk.CTkLabel(win, text="You are running v%s." % APP_VERSION, font=self.f_s,
                     text_color=PALETTE["muted"]).grid(
            row=1, column=0, sticky="w", padx=24, pady=(0, 12))
        ctk.CTkLabel(win, text="What's new", font=self.f_bb,
                     text_color=PALETTE["text"]).grid(
            row=2, column=0, sticky="w", padx=24, pady=(0, 4))
        notes = (info.notes or "").strip() or "No release notes were published."
        box = ctk.CTkTextbox(win, font=self.f_b, wrap="word", corner_radius=10,
                             fg_color=card, text_color=PALETTE["text"])
        box.grid(row=3, column=0, sticky="nsew", padx=24)
        try:
            box.insert("1.0", notes)
            box.configure(state="disabled")
        except Exception:
            pass
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.grid(row=4, column=0, sticky="ew", padx=24, pady=(14, 20))

        def _close():
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass
            self._upd_popup = None

        def _update_now():
            self._upd_found = info
            _close()
            try:
                self._show("about")
            except Exception:
                pass
            self._do_install_update()

        ctk.CTkButton(row, text="  Update and restart", height=38, width=210,
                      corner_radius=10, font=self.f_bb, fg_color=PALETTE["primary"],
                      text_color="#ffffff", hover_color=PALETTE["primary_hover"],
                      command=_update_now).pack(side="left")
        ctk.CTkButton(row, text="Later", height=38, width=110, corner_radius=10,
                      font=self.f_bb, fg_color=PALETTE["neutral"],
                      text_color=PALETTE["text"], hover_color=PALETTE["neutral_hover"],
                      command=_close).pack(side="left", padx=(10, 0))
        win.protocol("WM_DELETE_WINDOW", _close)
        # CTkToplevel needs a beat before it can take the grab, or the window
        # opens behind the main one on Windows.
        try:
            win.after(220, win.lift)
            win.after(260, win.focus_force)
            win.after(300, win.grab_set)
        except Exception:
            pass
        return win

    def _do_install_update(self):
        from tkinter import messagebox

        info = getattr(self, "_upd_found", None)
        up = self._updater()
        if not (info and up):
            return
        if not messagebox.askyesno(
                "Update to %s" % info.version,
                "Download version %s and install it now?\n\nThe app will close, update "
                "itself and reopen. Your settings are kept." % info.version):
            return
        if getattr(self, "_upd_busy", False):
            return
        self._upd_busy = True
        try:
            self._upd_install.configure(state="disabled")
            self._upd_btn.configure(state="disabled")
            self._upd_bar.set(0)
            self._upd_bar.grid()
        except Exception:
            pass
        self._upd_say("Downloading version %s..." % info.version)
        threading.Thread(target=self._upd_download_worker, args=(up, info), daemon=True).start()

    def _upd_download_worker(self, up, info):
        def progress(frac):
            self.after(0, lambda: self._upd_progress(frac))

        try:
            ok, result = up.download(info, progress=progress)
        except Exception as exc:
            ok, result = False, "Download failed: %s" % exc
        self.after(0, lambda: self._upd_downloaded(up, ok, result))

    def _upd_progress(self, frac):
        try:
            self._upd_bar.set(max(0.0, min(1.0, float(frac))))
            self._upd_say("Downloading... %d%%" % int(frac * 100))
        except Exception:
            pass

    def _upd_downloaded(self, up, ok, result):
        self._upd_busy = False
        try:
            self._upd_install.configure(state="normal")
            self._upd_btn.configure(state="normal")
        except Exception:
            pass
        if not ok:
            try:
                self._upd_bar.grid_remove()
            except Exception:
                pass
            self._upd_say(str(result), "stop")
            return
        self._upd_say("Installing - the app will close and reopen...", "primary")
        started, msg = up.install(result)
        if not started:
            self._upd_say(msg, "stop")
            return
        self.after(400, self._upd_quit)

    def _upd_quit(self):
        try:
            self._preview_on = False
            self._stop_tray()
        except Exception:
            pass
        try:
            self.relay.shutdown()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        os._exit(0)

    def _on_theme(self, _value=None):
        mode = (self._theme_var.get() or "Light").lower()
        if mode not in ("light", "dark"):
            mode = "light"
        ctk.set_appearance_mode(mode)
        _set(self.relay.cfg, ["ui", "theme"], mode)
        try:
            self.save_config(self.relay.cfg, self.relay.config_path)
        except Exception:
            pass

    def _input_status_text(self):
        try:
            return self.relay.input_status_text()
        except Exception:
            return "Chat log: unavailable"

    def _refresh_target(self):
        text = self._input_status_text()
        try:
            self._target_lbl.configure(text=text)
        except Exception:
            pass
        lbl = getattr(self, "_input_status_lbl", None)
        if lbl is not None:
            try:
                lbl.configure(text=text)
            except Exception:
                pass

    def _do_detect(self):
        def _work():
            try:
                self.relay.detect_chat_log()
            except Exception as exc:
                self.relay._log(f"Detect failed: {exc}")
            try:
                self.after(0, self._refresh_target)
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _do_browse(self):
        from tkinter import filedialog

        initial = ""
        try:
            cur = self.relay.chat_log_path()
            initial = os.path.dirname(cur) if cur else ""
        except Exception:
            initial = ""
        path = filedialog.askopenfilename(
            parent=self,
            title="Select your RAGE MP .storage chat log file",
            initialdir=initial or None,
            filetypes=[("RAGE MP storage", ".storage"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.relay.set_chat_log_path(path)
        except Exception as exc:
            self.relay._log(f"Could not set the chat log path: {exc}")
        self._render_settings()
        self._refresh_target()

    def _do_mdc_toggle(self):
        from tkinter import messagebox

        cfg = self.relay.cfg.setdefault("mdc_lookup", {})
        turning_on = not bool(cfg.get("enabled"))
        if turning_on:
            if not messagebox.askyesno(
                "Enable MDC lookups - use at your own risk",
                "USE AT YOUR OWN RISK.\n\n"
                "MDC lookups automate a logged-in GTA World website using your own session. "
                "Automating a logged-in site may breach GTA World's rules, and any consequences "
                "for your account are yours alone.\n\n"
                "It is read-only: nothing is ever submitted or changed. You log in yourself in a "
                "real browser window, and only the session cookie is stored, encrypted.\n\n"
                "Enable MDC lookups?",
                icon="warning", parent=self):
                return
        cfg["enabled"] = turning_on
        saver = getattr(self, "save_config", None) or getattr(self, "_save_config", None)
        try:
            if callable(saver):
                saver(self.relay.cfg)
            self.relay.apply_config()
        except Exception as exc:
            self.relay._log(f"Could not change the MDC setting: {exc}")
        self._render_settings()
        if turning_on:
            messagebox.showinfo(
                "MDC lookups enabled",
                "MDC lookups are ON. Ask for a code ten or a plate on the radio and the result "
                "is read back to you.\n\nLog in with the Log in button above if you have not "
                "already. Turn this off at any time.",
                parent=self)
        else:
            messagebox.showinfo("MDC lookups disabled",
                                "MDC lookups are OFF. No requests will be sent.", parent=self)

    def _do_browse_file(self, entry, field):
        from tkinter import filedialog

        cur = entry.get().strip()
        initial = os.path.dirname(cur) if cur else ""
        path = filedialog.askopenfilename(
            parent=self, title="Select " + str(field.get("label", "file")).lower(),
            initialdir=initial or None,
            filetypes=field.get("filetypes") or [("All files", "*.*")])
        if not path:
            return
        try:
            base = os.path.abspath(SCRIPT_DIR) if "SCRIPT_DIR" in globals() else None
            if base and os.path.abspath(path).startswith(base + os.sep):
                path = os.path.relpath(path, base).replace("\\", "/")
        except Exception:
            pass
        entry.delete(0, "end")
        entry.insert(0, path)

    def _do_start(self):
        self.relay.start()

    def _do_test(self):
        threading.Thread(target=self.relay.speak_test, daemon=True).start()


    def _mdc_status_text(self):
        try:
            return self.relay.mdc_status_text()
        except Exception:
            return "Unavailable"

    def _refresh_mdc_label(self):
        if getattr(self, "_mdc_status_lbl", None) is not None:
            try:
                self._mdc_status_lbl.configure(text=self._mdc_status_text())
            except Exception:
                pass

    def _do_mdc_login(self):
        if getattr(self, "_mdc_status_lbl", None) is not None:
            try:
                self._mdc_status_lbl.configure(text="Opening browser - log in, then close it...")
            except Exception:
                pass

        def _worker():
            try:
                ok, msg = self.relay.mdc_login()
            except Exception as e:
                ok, msg = False, str(e)
            def _done():
                self._refresh_mdc_label()
                try:
                    self._flash_hint("MDC: " + (msg or ("Logged in" if ok else "Login failed")), ok=ok)
                except Exception:
                    pass
            try:
                self.after(0, _done)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _do_mdc_logout(self):
        try:
            ok, msg = self.relay.mdc_logout()
        except Exception as e:
            ok, msg = False, str(e)
        self._refresh_mdc_label()
        try:
            self._flash_hint("MDC: " + (msg or ("Logged out" if ok else "Nothing to clear")), ok=ok)
        except Exception:
            pass

    def _make_readonly(self, textbox):
        def _block(event):
            ctrl = bool(event.state & 0x4)
            if ctrl and event.keysym.lower() in ("c", "a"):
                return None
            if event.keysym in ("Left", "Right", "Up", "Down", "Home", "End",
                                 "Prior", "Next", "Shift_L", "Shift_R",
                                 "Control_L", "Control_R"):
                return None
            return "break"
        try:
            textbox.bind("<Key>", _block)
        except Exception:
            pass

    @staticmethod
    def _est_text_height(text, width_chars=90, line_px=20, pad=18):
        import math
        lines = 0
        for ln in text.split("\n"):
            lines += max(1, math.ceil(len(ln) / width_chars))
        return int(lines * line_px + pad)

    def _clear_recent(self):
        try:
            self.relay.recent.clear()
        except Exception:
            pass
        self._recent_sig = None
        self._render_recent()

    def _toggle_preview(self):
        self._preview_on = not getattr(self, "_preview_on", False)
        if self._preview_on:
            self._preview_btn.configure(text="  Hide Chat")
            self._preview_box.grid()
            self._render_preview(force=True)
        else:
            self._preview_btn.configure(text="  Show Chat")
            self._preview_box.grid_remove()

    def _render_preview(self, force=False):
        if not getattr(self, "_preview_on", False):
            return
        try:
            lines = list(getattr(self.relay, "input_preview", []))
        except Exception:
            lines = []
        sig = (len(lines), lines[-1] if lines else None)
        if not force and sig == getattr(self, "_preview_sig", None):
            return
        self._preview_sig = sig
        body = "\n".join(lines) if lines else (
            "No chat read yet.\n\n"
            "Press Start, then send or receive a message in game. Lines appear here "
            "exactly as the app parsed them: (channel) sender: text"
        )
        try:
            self._preview_box.configure(state="normal")
            self._preview_box.delete("1.0", "end")
            self._preview_box.insert("end", body)
            self._preview_box.see("end")
            self._preview_box.configure(state="disabled")
        except Exception:
            pass

    def _tick(self):
        running = self.relay.is_running()
        pending = self.relay.player.pending()
        speaking = running and pending > 0
        if speaking:
            color, txt, sub = PALETTE["speak"], "Speaking", "Playing dispatch audio"
        elif running:
            color, txt, sub = PALETTE["live"], "Listening", "Reading the game chat log"
        else:
            color, txt, sub = PALETTE["idle"], "Idle", "Not watching"
        self._status_dot.configure(text_color=color)
        self._status_text.configure(text=txt)
        self._status_sub.configure(text=sub)
        self._side_status.configure(
            text="\u25cf" if self._sidebar_collapsed else f"\u25cf  {txt}", text_color=color)
        self._side_queue.configure(text=f"queue: {pending}")

        self._render_recent()
        self._render_log()
        self._render_debug()
        self._render_preview()
        self.after(700, self._tick)

    def _render_recent(self):
        items = list(self.relay.recent)
        sig = (len(items), items[0]["time"] if items else None,
               items[0]["dispatch"] if items else None)
        if sig == self._recent_sig:
            return
        self._recent_sig = sig
        for child in self._recent_frame.winfo_children():
            child.destroy()
        if not items:
            ctk.CTkLabel(self._recent_frame, text="No calls yet.", font=self.f_b,
                         text_color=PALETTE["muted"]).grid(row=0, column=0, sticky="w",
                                                           padx=14, pady=14)
            return
        for i, item in enumerate(items):
            disp = item.get("dispatch") or ""
            skipped = disp.startswith("(skipped")
            header = f"[{item['time']}]  {item['raw']}"
            text = header + ("\n" + disp if disp else "")
            box = ctk.CTkTextbox(self._recent_frame, font=self.f_b, corner_radius=10,
                                 fg_color=PALETTE["card_alt"], text_color=PALETTE["text"],
                                 border_width=0, wrap="word", activate_scrollbars=False,
                                 height=self._est_text_height(text))
            box.grid(row=i, column=0, sticky="ew", padx=8, pady=5)
            box.insert("1.0", text)
            try:
                box.tag_add("hdr", "1.0", "1.end")
                box.tag_config("hdr", foreground=PALETTE["text"])
                if disp:
                    box.tag_add("disp", "2.0", "end")
                    box.tag_config(
                        "disp",
                        foreground=PALETTE["muted"] if skipped else PALETTE["primary"],
                    )
            except Exception:
                pass
            self._make_readonly(box)

    def _render_log(self):
        text = "\n".join(self._log_lines)
        if getattr(self, "_last_log", None) == text:
            return
        self._last_log = text
        self._log_box.delete("1.0", "end")
        self._log_box.insert("end", text)
        self._log_box.see("end")

    def _build_bugs(self):
        page = ctk.CTkScrollableFrame(self._container, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(page, text="Report a bug", font=self.f_title,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w",
                                                       padx=26, pady=(22, 4))
        ctk.CTkLabel(page, text="Send a bug straight to the developer, and watch the live diagnostics console.",
                     font=self.f_b, text_color=PALETTE["muted"]).grid(
            row=1, column=0, sticky="w", padx=26, pady=(0, 8))

        form = self._card(page)
        form.grid(row=2, column=0, sticky="ew", padx=22, pady=8)
        form.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(form, text="What went wrong?", font=self.f_h,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        self._bug_entry = ctk.CTkTextbox(form, height=120, font=self.f_b, corner_radius=10,
                                         fg_color=PALETTE["card_alt"], text_color=PALETTE["text"],
                                         border_width=0, wrap="word")
        self._bug_entry.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        ctk.CTkLabel(form, text="Contact (optional \u2014 Discord handle or email so the dev can follow up)",
                     font=self.f_s, text_color=PALETTE["muted"]).grid(row=2, column=0, sticky="w", padx=16)
        self._bug_contact = ctk.CTkEntry(form, font=self.f_b, corner_radius=10,
                                         fg_color=PALETTE["card_alt"], border_width=0)
        self._bug_contact.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 8))
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        actions.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(actions, text="  Send bug report", image=self._icon("flag", 16, IC_WHITE),
                      compound="left", font=self.f_bb, height=40, corner_radius=10,
                      fg_color=PALETTE["primary"], hover_color=PALETTE["primary_hover"],
                      command=self._send_bug).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(actions, text="Save to file", width=110, height=40, corner_radius=10,
                      font=self.f_bb, fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"],
                      command=self._save_bug_report).grid(row=0, column=2, sticky="e", padx=6)
        ctk.CTkButton(actions, text="Copy", width=80, height=40, corner_radius=10,
                      font=self.f_bb, fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"],
                      command=self._copy_bug_report).grid(row=0, column=3, sticky="e", padx=6)
        ctk.CTkButton(actions, text="Open folder", width=110, height=40, corner_radius=10,
                      font=self.f_bb, fg_color=PALETTE["neutral"], text_color=PALETTE["text"],
                      hover_color=PALETTE["neutral_hover"],
                      command=self._open_report_folder).grid(row=0, column=4, sticky="e", padx=6)
        self._bug_status = ctk.CTkLabel(actions, text="", font=self.f_b, text_color=PALETTE["muted"],
                                       wraplength=420, justify="left")
        self._bug_status.grid(row=1, column=0, columnspan=5, sticky="w", padx=2, pady=(8, 0))
        ctk.CTkLabel(form, text="Reports are rate-limited and stripped of API keys and other secrets before sending.",
                     font=self.f_s, text_color=PALETTE["muted"]).grid(row=5, column=0, sticky="w", padx=16, pady=(0, 12))

        console = self._card(page)
        console.grid(row=3, column=0, sticky="nsew", padx=22, pady=8)
        console.grid_columnconfigure(0, weight=1)
        console.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(console, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="Diagnostics console", font=self.f_h,
                     text_color=PALETTE["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Copy", width=64, height=28, corner_radius=8,
                      font=self.f_s, fg_color=PALETTE["card_alt"], text_color=PALETTE["text"],
                      hover_color=PALETTE["primary_hover"], command=self._copy_debug).grid(row=0, column=2, sticky="e", padx=(6, 0))
        ctk.CTkButton(header, text="Clear", width=64, height=28, corner_radius=8,
                      font=self.f_s, fg_color=PALETTE["card_alt"], text_color=PALETTE["text"],
                      hover_color=PALETTE["primary_hover"], command=self._clear_debug).grid(row=0, column=3, sticky="e", padx=(6, 0))
        self._debug_box = ctk.CTkTextbox(console, height=280, font=self.f_mono, corner_radius=10,
                                         fg_color="#0f172a", text_color="#8ef0a6",
                                         border_width=0, wrap="none")
        self._debug_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self._debug_box.configure(state="disabled")
        return page

    def _send_bug(self):
        msg = self._bug_entry.get("1.0", "end").strip()
        contact = self._bug_contact.get().strip()
        try:
            ok, info = self.relay.report_bug(msg, contact)
        except Exception as exc:
            ok, info = False, f"Could not send: {exc}"
        self._bug_status.configure(text=info,
                                   text_color=PALETTE["start"] if ok else PALETTE["stop"])
        if ok:
            self._bug_entry.delete("1.0", "end")

    def _report_dir(self):
        from modules import app_paths

        path = os.path.join(app_paths.user_data_dir(), "bug_reports")
        os.makedirs(path, exist_ok=True)
        return path

    def _bug_report_text(self):
        import platform
        from modules import app_paths

        msg = self._bug_entry.get("1.0", "end").strip()
        contact = self._bug_contact.get().strip()
        try:
            target = self.relay.chat_log_path() or "(not resolved)"
        except Exception:
            target = "(unknown)"
        tts = _get(self.relay.cfg, ["tts", "provider"], "?")
        head = [
            f"911 Dispatch Relay {APP_VERSION} bug report",
            f"When: {datetime.now().isoformat(timespec='seconds')}",
            f"OS: {platform.platform()}  Python: {platform.python_version()}",
            f"Installed build: {'yes' if app_paths.is_frozen() else 'no (running from source)'}",
            f"Config: {getattr(self.relay, 'config_path', '?')}",
            f"Chat log: {target}",
            f"Voice: {tts}   Running: {'yes' if self.relay.is_running() else 'no'}",
            f"Contact: {contact or '(none given)'}",
            "",
            "What went wrong:",
            msg or "(nothing written)",
            "",
            "Recent log:",
        ]
        return "\n".join(head + list(self._log_lines)[-60:])

    def _save_bug_report(self):
        try:
            name = "bug-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".txt"
            path = os.path.join(self._report_dir(), name)
            with io.open(path, "w", encoding="utf-8") as fh:
                fh.write(self._bug_report_text())
        except Exception as exc:
            self._bug_status.configure(text=f"Could not save the report: {exc}",
                                       text_color=PALETTE["stop"])
            return
        self._bug_status.configure(text=f"Saved to {path}", text_color=PALETTE["start"])

    def _copy_bug_report(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self._bug_report_text())
            self._bug_status.configure(
                text="Report copied - paste it to the dev on Discord.",
                text_color=PALETTE["start"])
        except Exception as exc:
            self._bug_status.configure(text=f"Could not copy: {exc}",
                                       text_color=PALETTE["stop"])

    def _open_report_folder(self):
        try:
            path = self._report_dir()
            if os.name == "nt":
                os.startfile(path)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
            self._bug_status.configure(text=path, text_color=PALETTE["muted"])
        except Exception as exc:
            self._bug_status.configure(text=f"Could not open the folder: {exc}",
                                       text_color=PALETTE["stop"])

    def _clear_debug(self):
        self._log_lines.clear()
        self._last_debug = None
        self._render_debug()

    def _copy_debug(self):
        try:
            self.clipboard_clear()
            self.clipboard_append("\n".join(self._log_lines))
        except Exception:
            pass

    def _render_debug(self):
        box = getattr(self, "_debug_box", None)
        if box is None:
            return
        debug_on = bool(_get(self.relay.cfg, ["ui", "debug"], False))
        lines = list(self._log_lines)
        if not debug_on:
            lines = [ln for ln in lines if any(
                h in ln.lower() for h in
                ("error", "failed", "exception", "traceback", "warn", "could not", "unavailable"))]
        text = "\n".join(lines)
        if not text:
            text = "Waiting for activity\u2026" if debug_on else "No errors or warnings logged."
        if text == self._last_debug:
            return
        self._last_debug = text
        try:
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("end", text)
            box.see("end")
            box.configure(state="disabled")
        except Exception:
            pass

    def _min_to_tray_enabled(self):
        return bool(_get(self.relay.cfg, ["ui", "minimize_to_tray"], False))

    def _on_unmap(self, event):
        if event.widget is not self:
            return
        if not self._min_to_tray_enabled():
            return
        try:
            if self.state() != "iconic":
                return
        except Exception:
            return
        self._hide_to_tray()

    def _hide_to_tray(self):
        if self._tray_icon is not None:
            return
        try:
            import pystray
            from PIL import Image
        except Exception:
            return
        image = self._tray_image(Image)
        menu = pystray.Menu(
            pystray.MenuItem("Show 911 Dispatch Relay", self._tray_show, default=True),
            pystray.MenuItem("Quit", self._tray_quit),
        )
        self._tray_icon = pystray.Icon("dispatch_relay", image, "911 Dispatch Relay", menu)
        self.after(0, self.withdraw)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _tray_image(self, Image):
        try:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            p = os.path.join(base, "assets", "app.ico")
            if os.path.exists(p):
                return Image.open(p)
        except Exception:
            pass
        return Image.new("RGB", (64, 64), (37, 99, 235))

    def _tray_show(self, icon=None, item=None):
        self.after(0, self._restore_from_tray)

    def _restore_from_tray(self):
        try:
            self.deiconify()
            self.state("normal")
            self.lift()
            self.focus_force()
        except Exception:
            pass
        self._stop_tray()

    def _stop_tray(self):
        ic = self._tray_icon
        self._tray_icon = None
        if ic is not None:
            try:
                ic.stop()
            except Exception:
                pass

    def _tray_quit(self, icon=None, item=None):
        self._stop_tray()
        self.after(0, self._on_close)

    def _on_close(self):
        self._preview_on = False
        self._stop_tray()
        try:
            self.relay.shutdown()
        finally:
            self.destroy()


def run_app(relay, save_config):
    try:
        ctk.deactivate_automatic_dpi_awareness()
    except Exception:
        pass
    app = DispatchApp(relay, save_config)
    app.mainloop()
