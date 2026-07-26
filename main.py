#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import queue
import re
import threading
import time
from collections import deque
from datetime import datetime

import numpy as np
import yaml

from modules import app_paths
from modules.hotkeys import HotkeyManager
from modules.file_watcher import (
    FileWatcher,
    StorageReadError,
    autodetect_storage_path,
    parse_block,
    strip_timestamps,
)
from modules.flagger import Flagger
from modules.llm import LLMProcessor, spell_plates, strip_ten_codes
from modules.player import AudioPlayer
from modules.radiofx import RadioFX
from modules.reporter import Reporter
from modules.mdc_lookup import MDCManager
from modules.tts import TTSEngine

APP_VERSION = "1.5.1"

BUNDLE_DIR = app_paths.bundle_dir()
DEFAULT_CONFIG_PATH = os.path.join(BUNDLE_DIR, "config.yaml")
CONFIG_PATH = app_paths.ensure_user_config(DEFAULT_CONFIG_PATH)
SCRIPT_DIR = BUNDLE_DIR


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base or {})
    for key, val in (over or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _read_yaml(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_config(path: str = CONFIG_PATH) -> dict:
    defaults = {}
    if os.path.abspath(DEFAULT_CONFIG_PATH) != os.path.abspath(path):
        defaults = _read_yaml(DEFAULT_CONFIG_PATH)
    if not os.path.exists(path):
        if not defaults:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        save_config(defaults, path)
        return defaults
    user = _read_yaml(path)
    if not defaults:
        return user
    merged = _deep_merge(defaults, user)
    if merged != user:
        try:
            save_config(merged, path)
        except Exception:
            pass
    return merged


def save_config(cfg: dict, path: str = CONFIG_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)


class AlertSound:
    def __init__(self, cfg: dict, base_dir: str):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.volume = float(cfg.get("volume", 0.9))
        self.gap_ms = int(cfg.get("gap_ms", 150))
        self._samples: np.ndarray | None = None
        self._sr: int | None = None

        candidates = []
        p = cfg.get("path")
        if p:
            candidates.append(p if os.path.isabs(p) else os.path.join(base_dir, p))
        candidates.append(os.path.join(base_dir, "assets", "dispatch_alert.wav"))
        candidates.append(os.path.join(base_dir, "dispatch_alert.wav"))
        self.path = next((c for c in candidates if os.path.exists(c)), None)
        if self.enabled and self.path:
            self._load()

    def _load(self) -> None:
        try:
            import soundfile as sf

            data, sr = sf.read(self.path, dtype="float32", always_2d=False)
            if getattr(data, "ndim", 1) > 1:
                data = data.mean(axis=1)
            self._samples = data.astype(np.float32) * self.volume
            self._sr = int(sr)
        except Exception:
            self._samples = None
            self._sr = None

    def available(self) -> bool:
        return self._samples is not None and len(self._samples) > 0

    def _resample(self, target_sr: int) -> np.ndarray:
        if self._sr == target_sr:
            return self._samples
        n = int(round(len(self._samples) * target_sr / float(self._sr)))
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        x_old = np.linspace(0.0, 1.0, num=len(self._samples), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
        return np.interp(x_new, x_old, self._samples).astype(np.float32)

    def prepend(self, samples: np.ndarray, sr: int) -> np.ndarray:
        if not self.available():
            return samples
        alert = self._resample(sr)
        gap = np.zeros(int(sr * self.gap_ms / 1000.0), dtype=np.float32)
        return np.concatenate([alert, gap, np.asarray(samples, dtype=np.float32)])


class DispatchRelay:
    def __init__(self, cfg: dict, config_path: str = CONFIG_PATH):
        self.cfg = cfg
        self.config_path = config_path
        self.recent: deque = deque(maxlen=int((cfg.get("ui") or {}).get("recent_limit", 20)))
        self._running = threading.Event()
        self._loop_thread: threading.Thread | None = None
        self._log_cb = None
        self.input_preview: deque = deque(maxlen=40)

        _flag_cfg = dict(cfg.get("flagging", {}) or {})
        _flag_cfg["own_callsigns"] = (cfg.get("location", {}) or {}).get("callsigns", [])
        _flag_cfg["mdc_lookup"] = cfg.get("mdc_lookup", {}) or {}
        self.flagger = Flagger(_flag_cfg)
        self.radiofx = RadioFX(cfg.get("radiofx", {}))
        self.player = AudioPlayer(cfg.get("playback", {}))
        self.llm = LLMProcessor(cfg.get("llm", {}))
        self.alert = AlertSound(cfg.get("alert", {}), base_dir=SCRIPT_DIR)
        self.reporter = Reporter(
            cfg.get("reporting", {}),
            app_version=APP_VERSION,
            log=lambda m: self._log(m, report=False),
        )

        self.mdc = MDCManager(
            cfg.get("mdc_lookup", {}) or {},
            llm=self.llm,
            log=self._log,
            speak=self._speak_text,
        )

        self.tts: TTSEngine | None = None
        self.watcher: FileWatcher | None = None

        self._synth_q: "queue.Queue" = queue.Queue(maxsize=32)
        self._synth_thread = threading.Thread(target=self._synth_worker, daemon=True)
        self._synth_thread.start()

        self.hotkeys = HotkeyManager(self.start, self.stop, log=self._log)
        self.apply_hotkeys()

    def set_log_callback(self, cb) -> None:
        self._log_cb = cb

    _ERROR_RE = re.compile(
        r"\b(?:error|errors|failed|failure|exception|traceback|crashed|"
        r"could not|cannot|unable to)\b",
        re.I,
    )
    _NO_REPORT_PREFIXES = ("DISPATCH:", "FLAGGED:", "MDC: ", "CHAT:", "RADIO:")

    def _log(self, msg: str, report: bool = True) -> None:
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        if self._log_cb:
            try:
                self._log_cb(line)
            except Exception:
                pass
        if report and not str(msg).startswith(self._NO_REPORT_PREFIXES):
            if self._ERROR_RE.search(str(msg)):
                try:
                    self.reporter.report_error(line)
                except Exception:
                    pass

    def report_bug(self, message: str, contact: str = "") -> tuple[bool, str]:
        try:
            return self.reporter.report_bug(message, contact)
        except Exception as e:
            return False, f"Could not send report: {e}"

    def _speak_text(self, text: str, summary: str = "", alert: bool = True) -> None:
        if not text or not text.strip():
            return
        text = spell_plates(strip_ten_codes(text))
        self._log(f"DISPATCH: {text}")
        self.recent.appendleft(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "raw": summary or "[MDC]",
                "dispatch": text,
            }
        )
        try:
            self._synth_q.put_nowait((text, alert))
        except queue.Full:
            self._log("Synth queue full -- dropped an MDC response.")

    def mdc_login(self) -> tuple[bool, str]:
        try:
            from modules.mdc_auth import login_interactive
            return login_interactive(self.cfg.get("mdc_lookup", {}), log=self._log)
        except Exception as e:
            return False, f"MDC login failed: {e}"

    def mdc_logout(self) -> tuple[bool, str]:
        try:
            from modules.mdc_auth import MDCSession
            ok, msg = MDCSession(self.cfg.get("mdc_lookup", {}), log=self._log).clear()
            self._log(f"MDC: {msg}")
            return ok, msg
        except Exception as e:
            return False, f"MDC logout failed: {e}"

    def mdc_status(self) -> dict:
        try:
            return self.mdc.status()
        except Exception:
            return {"enabled": False, "logged_in": False, "encryption": False, "session_ok": True}

    def mdc_status_text(self) -> str:
        try:
            return self.mdc.status_text()
        except Exception:
            return "Unavailable"

    def is_running(self) -> bool:
        return self._running.is_set()

    def _ensure_pipeline(self) -> None:
        if self.tts is None:
            self.tts = TTSEngine(self.cfg.get("tts", {}))

    def _input_cfg(self) -> dict:
        return dict(self.cfg.get("input_source", {}) or {})

    def _fingerprint(self) -> str:
        return str(self._input_cfg().get("server_fingerprint") or "GTA World")

    def chat_log_path(self) -> str:
        cfg = self._input_cfg()
        path = str(cfg.get("path") or "").strip()
        if path and os.path.isfile(path):
            return path
        if cfg.get("auto_detect", True):
            found = autodetect_storage_path(self._fingerprint())
            if found:
                return found
        return path

    def detect_chat_log(self) -> str:
        found = autodetect_storage_path(self._fingerprint())
        if not found:
            self._log(
                "Could not find a RAGE MP .storage file automatically. Set the "
                "path yourself in Settings > Chat log input - it looks like "
                r"C:\RAGEMP\client_resources\<hash>\.storage"
            )
            return ""
        self.set_chat_log_path(found)
        return found

    def set_chat_log_path(self, path: str) -> None:
        self.cfg.setdefault("input_source", {})["path"] = str(path or "")
        save_config(self.cfg, self.config_path)
        self._log(f"Chat log file set: {path}")

    def input_status_text(self) -> str:
        path = self.chat_log_path()
        if not path:
            return "Chat log: not set - press Detect"
        if not os.path.isfile(path):
            return f"Chat log: MISSING - {path}"
        return f"Chat log: {path}"

    def _has_target(self) -> bool:
        path = self.chat_log_path()
        return bool(path) and os.path.isfile(path)

    def start(self) -> None:
        if self._running.is_set():
            return
        if not self._has_target():
            self._log(
                "No chat log file set. Press Detect on the Dashboard, or point "
                "input_source.path at your RAGE MP .storage file."
            )
            return
        try:
            self._ensure_pipeline()
        except Exception as e:
            self._log(f"Init error: {e}")
            return
        self._running.set()
        self._loop_thread = threading.Thread(target=self._loop, daemon=True)
        self._loop_thread.start()
        self._log("Started.")

    def stop(self) -> None:
        if self._running.is_set():
            self._running.clear()
            self._drain_synth_queue()
            self.player.flush()
            self._log("Stopping...")

    def _drain_synth_queue(self) -> None:
        try:
            while True:
                self._synth_q.get_nowait()
                self._synth_q.task_done()
        except queue.Empty:
            pass

    def shutdown(self) -> None:
        self.stop()
        try:
            self.hotkeys.clear()
        except Exception:
            pass
        try:
            self.mdc.shutdown()
        except Exception:
            pass
        try:
            self._synth_q.put_nowait(None)
        except queue.Full:
            pass
        self.player.stop()

    def _loop(self) -> None:
        try:
            watcher = FileWatcher(self._input_cfg(), log=self._log)
            watcher.start()
        except Exception as e:
            self._log(f"Chat log error: {e}")
            self._running.clear()
            return
        self.watcher = watcher
        self._log(f"Watching chat log: {watcher.resolved_path}")
        while self._running.is_set():
            try:
                for frame in watcher.next_frames(timeout=0.4):
                    if not frame:
                        continue
                    self._note_input(frame)
                    for flag in self.flagger.process(strip_timestamps(frame)):
                        self._handle_flag(flag)
            except Exception as e:
                self._log(f"Loop error: {e}")
                time.sleep(0.5)
        try:
            watcher.stop()
        except Exception:
            pass
        self.watcher = None
        self._log("Stopped.")

    def _note_input(self, frame) -> None:
        try:
            msg = parse_block(frame)
        except Exception:
            return
        self.input_preview.append(str(msg))
    @staticmethod
    def _summary(flag: dict) -> str:
        if flag.get("type") == "call":
            inc = flag.get("incident") or "----"
            loc = flag.get("location") or "unknown"
            return f"Incident {inc}: {flag.get('situation', '')} @ {loc}"
        if flag.get("type") == "panic":
            who = flag.get("name") or flag.get("callsign") or "officer"
            loc = flag.get("location")
            return f"[PANIC] {who}" + (f" @ {loc}" if loc else "")
        if flag.get("type") == "cad":
            cs = flag.get("callsign") or "unit"
            return f"[CAD] {cs}: update {flag.get('what', 'CAD')}"
        if flag.get("type") == "code6":
            cs = flag.get("callsign") or "unit"
            loc = flag.get("location")
            return f"[CODE 6] {cs}" + (f" @ {loc}" if loc else "")
        if flag.get("type") == "code7":
            cs = flag.get("callsign") or "unit"
            loc = flag.get("location")
            return f"[CODE 7] {cs}" + (f" @ {loc}" if loc else "")
        if flag.get("type") == "clear":
            cs = flag.get("callsign") or "unit"
            return f"[CLEAR] {cs}"
        if flag.get("type") == "mdc":
            cs = flag.get("callsign") or "unit"
            return f"[MDC {flag.get('lookup', '?')}] {cs}: {flag.get('target', '')}"
        if flag.get("type") == "radio":
            cs = flag.get("callsign")
            prefix = f"[RADIO {cs}] " if cs else "[RADIO] "
            return prefix + flag.get("body", "")
        return flag.get("body", "")

    def _handle_flag(self, flag: dict) -> None:
        summary = self._summary(flag)
        self._log(f"FLAGGED: {summary}")
        if isinstance(flag, dict) and flag.get("type") == "mdc":
            # _speak_text; they do not go through the 911 verify/AI path.
            try:
                self.mdc.handle(flag)
            except Exception as e:
                self._log(f"MDC error: {e}")
            return
        try:
            if not self.llm.verify_flag(flag):
                self._log("AI filter: not a real call -- skipped.")
                self.recent.appendleft(
                    {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "raw": summary,
                        "dispatch": "(skipped: AI filter)",
                    }
                )
                return
        except Exception as e:
            self._log(f"AI filter error (allowing): {e}")
        try:
            dispatch = self.llm.process(flag)
        except Exception as e:
            self._log(f"LLM error: {e}")
            dispatch = summary
        if not dispatch or not dispatch.strip():
            self._log("SKIPPED (non-emergency / landline): no TTS.")
            self.recent.appendleft(
                {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "raw": summary,
                    "dispatch": "(skipped: non-emergency)",
                }
            )
            return
        dispatch = spell_plates(strip_ten_codes(dispatch))
        self._log(f"DISPATCH: {dispatch}")
        self.recent.appendleft(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "raw": summary,
                "dispatch": dispatch,
            }
        )
        try:
            self._synth_q.put_nowait((dispatch, True))
        except queue.Full:
            self._log("Synth queue full -- dropped a call.")

    def _is_priority(self, text: str) -> bool:
        t = (text or "").lower()
        if "code 3" in t or "code three" in t:
            return True
        if "in distress" in t or "shots fired" in t or "officer down" in t:
            return True
        try:
            from modules.llm import _HIGH_RISK
            return bool(_HIGH_RISK.search(text or ""))
        except Exception:
            return False

    def _should_alert(self, text: str) -> bool:
        alert_cfg = self.cfg.get("alert", {}) or {}
        if not alert_cfg.get("enabled", True):
            return False
        scope = str(alert_cfg.get("scope", "all")).lower()
        if scope.startswith("prio") or scope in ("code3", "urgent", "high"):
            return self._is_priority(text)
        return True

    def speak_test(self) -> None:
        sample = {
            "type": "call",
            "incident": "7023",
            "situation": "459 in progress. Audible residential alarm triggered. Suspects reported on scene.",
            "location": "Hawick and Spanish",
            "raw": "Incident 7023: 459 in progress. Audible residential alarm triggered. Suspects reported on scene. @ Hawick and Spanish",
        }
        try:
            self._ensure_pipeline()
        except Exception as e:
            self._log(f"Init error: {e}")
            return
        self._running.set()
        self._handle_flag(sample)

    def _synth_worker(self) -> None:
        while True:
            item = self._synth_q.get()
            try:
                if item is None:
                    break
                if isinstance(item, tuple):
                    text, alert_ok = item
                else:
                    text, alert_ok = item, True
                if self.tts is None:
                    self._ensure_pipeline()
                samples, sr = self.tts.synthesize(text)
                samples, sr = self.radiofx.apply(samples, sr)
                if alert_ok and self._should_alert(text):
                    samples = self.alert.prepend(samples, sr)
                if not self._running.is_set():
                    continue
                if not self.player.enqueue(samples, sr):
                    self._log("Playback queue full -- dropped a call.")
            except Exception as e:
                self._log(f"TTS/FX error: {e}")
            finally:
                self._synth_q.task_done()

    def apply_config(self) -> None:
        _flag_cfg = dict(self.cfg.get("flagging", {}) or {})
        _flag_cfg["own_callsigns"] = (self.cfg.get("location", {}) or {}).get("callsigns", [])
        _flag_cfg["mdc_lookup"] = self.cfg.get("mdc_lookup", {}) or {}
        self.flagger = Flagger(_flag_cfg)
        self.radiofx = RadioFX(self.cfg.get("radiofx", {}))
        self.llm = LLMProcessor(self.cfg.get("llm", {}))
        self.alert = AlertSound(self.cfg.get("alert", {}), base_dir=SCRIPT_DIR)
        self.reporter = Reporter(
            self.cfg.get("reporting", {}),
            app_version=APP_VERSION,
            log=lambda m: self._log(m, report=False),
        )
        try:
            if getattr(self, "mdc", None):
                self.mdc.shutdown()
        except Exception:
            pass
        self.mdc = MDCManager(
            self.cfg.get("mdc_lookup", {}),
            llm=self.llm,
            log=self._log,
            speak=self._speak_text,
        )
        self.tts = None
        if self._running.is_set():
            try:
                self._ensure_pipeline()
            except Exception as e:
                self._log(f"Pipeline reinit error: {e}")
        try:
            limit = int((self.cfg.get("ui") or {}).get("recent_limit", 20))
            self.recent = deque(self.recent, maxlen=limit)
        except Exception:
            pass
        self.apply_hotkeys()
        self._log("Settings applied. (Playback device / volume changes take effect on restart.)")

    def apply_hotkeys(self) -> None:
        hk = self.cfg.get("hotkeys", {}) or {}
        mgr = getattr(self, "hotkeys", None)
        if mgr is None:
            return
        mgr.apply(
            start_key=str(hk.get("start") or "").strip(),
            stop_key=str(hk.get("stop") or "").strip(),
            enabled=bool(hk.get("enabled", True)),
        )


def run_cli(relay: DispatchRelay) -> None:
    if not relay._has_target():
        print("No chat log file set; trying to detect it...")
        if not relay.detect_chat_log():
            print("Could not find the RAGE MP .storage file. "
                  "Set input_source.path in config.yaml.")
            return
    relay.start()
    if not relay.is_running():
        return
    print("Running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
    finally:
        relay.shutdown()


def run_gui(relay: DispatchRelay) -> None:
    try:
        from modules.gui_app import run_app
        run_app(relay, save_config)
        return
    except Exception as e:
        print(f"Modern UI unavailable ({e}); using the classic UI.")
    run_gui_legacy(relay)


def run_gui_legacy(relay: DispatchRelay) -> None:
    import tkinter as tk
    from tkinter import scrolledtext

    accent, fg, bg, panel, sub = "#ff7a00", "#eaeaea", "#161616", "#0e0e0e", "#9a9a9a"

    root = tk.Tk()
    root.title("911 Dispatch Relay")
    root.geometry("640x620")
    root.configure(bg=bg)
    root.minsize(560, 540)

    header = tk.Frame(root, bg=bg)
    header.pack(fill="x", pady=(12, 2))
    tk.Label(header, text="\U0001F6A8  911 DISPATCH RELAY", fg=accent, bg=bg,
             font=("Consolas", 17, "bold")).pack()
    tk.Label(header, text="local chat-log dispatch  \u2022  audio to your speakers only",
             fg=sub, bg=bg, font=("Segoe UI", 9)).pack()

    status_var = tk.StringVar(value="\u25cb Idle")
    status_lbl = tk.Label(root, textvariable=status_var, fg=fg, bg=bg, font=("Consolas", 11, "bold"))
    status_lbl.pack(pady=(8, 4))

    target_var = tk.StringVar(value="")
    tk.Label(root, textvariable=target_var, fg=sub, bg=bg, font=("Consolas", 9)).pack(pady=(0, 4))

    def refresh_target():
        target_var.set(relay.input_status_text())

    btns = tk.Frame(root, bg=bg)
    btns.pack(pady=8)

    def styled(parent, text, cmd, primary=False, width=13):
        return tk.Button(parent, text=text, width=width, relief="flat", cursor="hand2",
                         bg=accent if primary else "#2a2a2a", fg="#111" if primary else fg,
                         activebackground="#ffa04d" if primary else "#3a3a3a",
                         font=("Segoe UI", 10, "bold"), command=cmd)

    def do_detect():
        threading.Thread(target=lambda: (relay.detect_chat_log(),
                                         root.after(0, refresh_target)),
                         daemon=True).start()

    def do_start():
        relay.start()

    def do_test():
        threading.Thread(target=relay.speak_test, daemon=True).start()

    styled(btns, "\u25b6 Start", do_start, primary=True, width=11).grid(row=0, column=0, padx=4)
    styled(btns, "\u25a0 Stop", relay.stop, width=9).grid(row=0, column=1, padx=4)
    styled(btns, "\u2316 Detect log", do_detect, width=13).grid(row=0, column=2, padx=4)
    styled(btns, "\U0001F50A Test", do_test, width=9).grid(row=0, column=3, padx=4)

    tk.Label(root, text="Recent calls", fg=accent, bg=bg,
             font=("Consolas", 11, "bold")).pack(anchor="w", padx=14, pady=(6, 0))
    recent_box = scrolledtext.ScrolledText(root, height=9, bg=panel, fg=fg, insertbackground=fg,
                                           font=("Consolas", 9), relief="flat", borderwidth=6)
    recent_box.pack(fill="both", expand=False, padx=14, pady=4)

    log_head = tk.Frame(root, bg=bg)
    log_head.pack(fill="x", padx=14)
    tk.Label(log_head, text="Log", fg=accent, bg=bg, font=("Consolas", 11, "bold")).pack(side="left")
    log_lines: deque = deque(maxlen=300)
    tk.Button(log_head, text="clear", relief="flat", bg=bg, fg=sub, cursor="hand2",
              font=("Segoe UI", 8), command=lambda: log_lines.clear()).pack(side="right")

    log_box = scrolledtext.ScrolledText(root, height=8, bg=panel, fg="#9fe89f", insertbackground=fg,
                                        font=("Consolas", 9), relief="flat", borderwidth=6)
    log_box.pack(fill="both", expand=True, padx=14, pady=(4, 12))
    relay.set_log_callback(log_lines.append)

    def refresh():
        running = relay.is_running()
        status_var.set(("\u25cf RUNNING" if running else "\u25cb Idle") + f"    |    play queue: {relay.player.pending()}")
        status_lbl.config(fg="#7dff7d" if running else fg)
        recent_box.delete("1.0", "end")
        for item in list(relay.recent):
            recent_box.insert("end", f"[{item['time']}] {item['raw']}\n")
            if item["dispatch"]:
                recent_box.insert("end", f"    \u2192 {item['dispatch']}\n")
        log_box.delete("1.0", "end")
        log_box.insert("end", "\n".join(log_lines))
        log_box.see("end")
        root.after(700, refresh)

    def on_close():
        relay.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh_target()
    refresh()
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="911 Dispatch Relay")
    parser.add_argument("--detect", action="store_true",
                        help="Locate the RAGE MP .storage chat log, save it to the config, and exit")
    parser.add_argument("--cli", action="store_true", help="Run headless (no GUI)")
    parser.add_argument("--config", default=CONFIG_PATH, help="Path to config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    relay = DispatchRelay(cfg, config_path=args.config)

    if args.detect:
        found = relay.detect_chat_log()
        print(f"Chat log: {found}" if found else "No RAGE MP .storage file found.")
        return

    mode = "cli" if args.cli else (cfg.get("ui") or {}).get("mode", "gui")
    if mode == "cli":
        run_cli(relay)
    else:
        try:
            run_gui(relay)
        except Exception as e:
            print(f"GUI unavailable ({e}); falling back to CLI.")
            run_cli(relay)


if __name__ == "__main__":
    main()
