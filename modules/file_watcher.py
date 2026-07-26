from __future__ import annotations

import glob
import html
import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field

CHAT_LOG_KEY = "chat_log"
SERVER_FINGERPRINT = "GTA World"
STORAGE_FILENAME = ".storage"


TS_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*")
DATE_HEADER_RE = re.compile(r"^\[DATE:\s*(.+?)\s*\|\s*TIME:\s*(.+?)\]\s*$", re.I)

RADIO_RE = re.compile(
    r"^\*+\s*\[S:\s*(?P<slot>\d+)\s*\|\s*CH:\s*(?P<chan>[^\]]+)\]\s*"
    r"(?P<sender>.+?)\s+says(?:\s*\[[^\]]*\])?(?:\s*\(to\s+(?P<to>[^)]*)\))?:\s*"
    r"(?P<text>.*)$",
    re.I,
)
HQ_RE = re.compile(r"^\[HQ\]\s*(?P<text>.*)$", re.I)
PM_RE = re.compile(
    r"^\(\(\s*PM\s+(?P<dir>from|to)\s*\((?P<id>\d+)\)\s*(?P<sender>[^:]+?):\s*"
    r"(?P<text>.*?)\s*\)\)\s*$",
    re.I,
)
OOC_RE = re.compile(
    r"^\(\(\s*\((?P<id>\d+)\)\s*(?P<sender>[^:]+?):\s*(?P<text>.*?)\s*\)\)\s*$"
)
ACTION_RE = re.compile(r"^>\s*(?P<text>.+)$")
PRIORITY_RE = re.compile(
    r"^\[!\]\s*(?P<sender>.+?)\s+says\s*\[(?P<level>[^\]]+)\]"
    r"(?:\s*\(to\s+(?P<to>[^)]*)\))?:\s*(?P<text>.*)$",
    re.I,
)
LOCAL_RE = re.compile(
    r"^(?P<sender>[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,3})\s+"
    r"(?P<verb>says|shouts|whispers|says\s*\[[^\]]*\])"
    r"(?:\s*\(to\s+(?P<to>[^)]*)\))?:\s*(?P<text>.*)$"
)
TAG_RE = re.compile(r"^\[(?P<tag>[A-Z][A-Z0-9 /_-]{1,20})\]\s*(?P<text>.*)$")

CALL_BANNER_RE = re.compile(
    r"\*{3,}\s*(?P<kind>EMERGENCY|NON[\s-]?EMERGENCY)\s+CALL\s*\*{3,}", re.I
)
CALL_FIELD_RE = re.compile(
    r"^\*?\s*(?P<label>log\s*number|phone\s*number|location|situation)\s*:", re.I
)
ONE_LINE_CALL_RE = re.compile(r"^(?:911|311)\s*\|", re.I)

CALLSIGN_RE = re.compile(r"\b(\d{1,2}[A-Za-z]{1,5}\d{1,3})\b")

MAX_CALL_BLOCK_LINES = 8


@dataclass
class ParsedMessage:
    raw: str
    time: str = ""
    channel: str = "unknown"
    sender: str = ""
    callsign: str = ""
    text: str = ""
    radio_slot: str = ""
    radio_channel: str = ""
    target: str = ""
    lines: list = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - display helper
        who = self.sender or "-"
        chan = self.channel
        if self.radio_channel:
            chan = f"{chan}:{self.radio_channel}"
        return f"[{self.time}] ({chan}) {who}: {self.text}"


def strip_timestamp(line: str) -> tuple[str, str]:
    m = TS_RE.match(line or "")
    if not m:
        return "", (line or "").strip()
    return m.group(1), line[m.end():].strip()


def _callsign(*texts: str) -> str:
    for t in texts:
        m = CALLSIGN_RE.search(t or "")
        if m:
            return m.group(1).upper()
    return ""


def parse_line(raw: str) -> ParsedMessage:
    raw = (raw or "").rstrip()
    stamp, body = strip_timestamp(raw)
    msg = ParsedMessage(raw=raw, time=stamp, text=body, lines=[raw])

    if DATE_HEADER_RE.match(raw):
        msg.channel = "date"
        return msg

    m = RADIO_RE.match(body)
    if m:
        msg.channel = "radio"
        msg.sender = m.group("sender").strip()
        msg.text = m.group("text").strip()
        msg.radio_slot = m.group("slot")
        msg.radio_channel = m.group("chan").strip().upper()
        msg.target = (m.group("to") or "").strip()
        msg.callsign = _callsign(msg.text)
        return msg

    m = PM_RE.match(body)
    if m:
        msg.channel = "pm"
        msg.sender = m.group("sender").strip()
        msg.text = m.group("text").strip()
        msg.target = m.group("dir").lower()
        return msg

    m = OOC_RE.match(body)
    if m:
        msg.channel = "ooc"
        msg.sender = m.group("sender").strip()
        msg.text = m.group("text").strip()
        return msg

    m = HQ_RE.match(body)
    if m:
        msg.channel = "hq"
        msg.text = m.group("text").strip()
        msg.callsign = _callsign(msg.text)
        return msg

    m = PRIORITY_RE.match(body)
    if m:
        msg.channel = "priority"
        msg.sender = m.group("sender").strip()
        msg.text = m.group("text").strip()
        msg.target = (m.group("to") or "").strip()
        return msg

    if CALL_BANNER_RE.search(body) or CALL_FIELD_RE.match(body) or ONE_LINE_CALL_RE.match(body):
        msg.channel = "call"
        return msg

    m = ACTION_RE.match(body)
    if m:
        msg.channel = "action"
        msg.text = m.group("text").strip()
        return msg

    m = LOCAL_RE.match(body)
    if m:
        verb = m.group("verb").lower()
        msg.channel = "shout" if verb.startswith("shout") else (
            "whisper" if verb.startswith("whisper") else "local")
        msg.sender = m.group("sender").strip()
        msg.text = m.group("text").strip()
        msg.target = (m.group("to") or "").strip()
        msg.callsign = _callsign(msg.text)
        return msg

    m = TAG_RE.match(body)
    if m:
        msg.channel = "tagged"
        msg.sender = m.group("tag").strip()
        msg.text = m.group("text").strip()
        return msg

    msg.channel = "system"
    return msg


def parse_block(lines) -> ParsedMessage:
    lines = [ln for ln in (lines or []) if str(ln).strip()]
    if not lines:
        return ParsedMessage(raw="")
    if len(lines) == 1:
        return parse_line(lines[0])
    stamp, first = strip_timestamp(lines[0])
    msg = ParsedMessage(raw="\n".join(lines), time=stamp, channel="call", lines=list(lines))
    kind = CALL_BANNER_RE.search(first)
    msg.sender = (kind.group("kind").upper().replace(" ", "-") + " CALL") if kind else "CALL"
    fields = {}
    for ln in lines[1:]:
        _, body = strip_timestamp(ln)
        m = CALL_FIELD_RE.match(body)
        if not m:
            continue
        label = re.sub(r"\s+", "_", m.group("label").strip().lower())
        fields[label] = body[m.end():].strip()
    parts = []
    if fields.get("situation"):
        parts.append(fields["situation"])
    if fields.get("location"):
        parts.append("@ " + fields["location"])
    msg.text = " ".join(parts) or first
    msg.target = fields.get("log_number", "")
    return msg


def _candidate_roots() -> list:
    roots = []
    env = os.environ.get("RAGEMP_ROOT") or os.environ.get("RAGEMP_DIR")
    if env:
        roots.append(env)
    if os.name == "nt":
        drives = [f"{c}:\\" for c in "CDEFGH" if os.path.isdir(f"{c}:\\")]
        for d in drives:
            roots.append(os.path.join(d, "RAGEMP"))
            roots.append(os.path.join(d, "Games", "RAGEMP"))
            roots.append(os.path.join(d, "Program Files", "RAGEMP"))
            roots.append(os.path.join(d, "Program Files (x86)", "RAGEMP"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(os.path.join(local, "RAGEMP"))
    else:
        roots.append(os.path.expanduser("~/RAGEMP"))
    seen, out = set(), []
    for r in roots:
        key = os.path.normcase(os.path.abspath(r))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def find_storage_candidates() -> list:
    found = []
    for root in _candidate_roots():
        pattern = os.path.join(root, "client_resources", "*", STORAGE_FILENAME)
        try:
            found.extend(glob.glob(pattern))
        except Exception:
            continue
    return found


def _peek(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def autodetect_storage_path(fingerprint: str = SERVER_FINGERPRINT) -> str:
    scored = []
    for path in find_storage_candidates():
        data = _peek(path)
        if not data:
            continue
        is_gtaw = str(data.get("server_version", "")).strip().lower() == fingerprint.strip().lower()
        has_chat = bool(str(data.get(CHAT_LOG_KEY) or "").strip())
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        scored.append(((1 if is_gtaw else 0, 1 if has_chat else 0, mtime), path))
    if not scored:
        return ""
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def strip_timestamps(lines):
    out = []
    for line in lines:
        _time, body = strip_timestamp(line)
        out.append(body if body.strip() else line)
    return out


class StorageReadError(Exception):
    pass


def read_chat_lines(path: str, encoding: str = "utf-8", attempts: int = 5,
                    delay: float = 0.15) -> list:
    last_err = None
    for attempt in range(max(1, int(attempts))):
        try:
            with open(path, "r", encoding=encoding, errors="replace") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise StorageReadError("unexpected .storage layout (not a JSON object)")
            blob = data.get(CHAT_LOG_KEY)
            if blob is None:
                raise StorageReadError(
                    f"'{CHAT_LOG_KEY}' is missing - is this the GTA World .storage file?"
                )
            text = html.unescape(str(blob))
            return [ln.rstrip("\r") for ln in text.split("\n") if ln.strip()]
        except (OSError, PermissionError, ValueError, StorageReadError) as exc:
            last_err = exc
            if attempt + 1 < max(1, int(attempts)):
                time.sleep(max(0.0, float(delay)))
    raise StorageReadError(str(last_err) if last_err else "unknown read error")


def _rfind_block(haystack: list, needle: list) -> int:
    n, m = len(haystack), len(needle)
    if m == 0 or m > n:
        return -1
    for start in range(n - m, -1, -1):
        if haystack[start:start + m] == needle:
            return start
    return -1


class ChatLogDiffer:
    ANCHOR_SIZES = (30, 16, 8, 4, 2, 1)

    def __init__(self, replay_last: int = 0):
        self.replay_last = max(0, int(replay_last or 0))
        self._prev = None
        self.resets = 0

    def reset(self) -> None:
        self._prev = None

    def new_lines(self, snapshot: list) -> list:
        prev = self._prev
        if prev is None:
            self._prev = list(snapshot)
            if self.replay_last:
                return list(snapshot[-self.replay_last:])
            return []
        if snapshot == prev:
            return []
        tried = set()
        for size in self.ANCHOR_SIZES:
            k = min(size, len(prev))
            if k in tried or k == 0:
                continue
            tried.add(k)
            idx = _rfind_block(snapshot, prev[-k:])
            if idx >= 0:
                self._prev = list(snapshot)
                return list(snapshot[idx + k:])
        self.resets += 1
        self._prev = list(snapshot)
        return []


class CallBlockAssembler:
    def __init__(self, stale_after: float = 3.0):
        self.stale_after = float(stale_after)
        self._buf = []
        self._started = 0.0

    def _flush(self) -> list:
        if not self._buf:
            return []
        frame, self._buf = self._buf, []
        self._started = 0.0
        return [frame]

    def feed(self, line: str) -> list:
        _, body = strip_timestamp(line)
        frames = []
        if CALL_BANNER_RE.search(body):
            frames.extend(self._flush())
            self._buf = [line]
            self._started = time.time()
            return frames
        if self._buf:
            m = CALL_FIELD_RE.match(body)
            if m:
                self._buf.append(line)
                label = m.group("label").strip().lower()
                if label == "situation" or len(self._buf) >= MAX_CALL_BLOCK_LINES:
                    frames.extend(self._flush())
                return frames
            frames.extend(self._flush())
        frames.append([line])
        return frames

    def flush_stale(self) -> list:
        if self._buf and self._started and (time.time() - self._started) > self.stale_after:
            return self._flush()
        return []


class FileWatcher:
    def __init__(self, cfg: dict | None = None, log=None):
        cfg = dict(cfg or {})
        self.cfg = cfg
        self._log_cb = log
        self.path = str(cfg.get("path") or "").strip()
        self.auto_detect = bool(cfg.get("auto_detect", True))
        self.encoding = str(cfg.get("encoding") or "utf-8")
        self.poll_interval = max(0.15, float(cfg.get("poll_interval", 0.75) or 0.75))
        self.debounce = max(0.0, float(cfg.get("debounce_ms", 250) or 0) / 1000.0)
        self.retry_attempts = max(1, int(cfg.get("retry_attempts", 5) or 5))
        self.retry_delay = max(0.0, float(cfg.get("retry_delay", 0.15) or 0.0))
        self.use_watchdog = bool(cfg.get("use_watchdog", True))
        self.fingerprint = str(cfg.get("server_fingerprint") or SERVER_FINGERPRINT)

        self.resolved_path = ""
        self.last_error = ""
        self.lines_seen = 0
        self._differ = ChatLogDiffer(replay_last=int(cfg.get("replay_last", 0) or 0))
        self._assembler = CallBlockAssembler()
        self._frames: queue.Queue = queue.Queue(maxsize=512)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer = None
        self._last_sig = None
        self._err_logged = ""

    def _log(self, msg: str) -> None:
        if self._log_cb:
            try:
                self._log_cb(msg)
                return
            except Exception:
                pass
        print(msg, flush=True)

    def resolve_path(self) -> str:
        if self.path and os.path.isfile(self.path):
            return self.path
        if self.path and not self.auto_detect:
            return self.path
        if self.auto_detect:
            found = autodetect_storage_path(self.fingerprint)
            if found:
                return found
        return self.path

    def status_text(self) -> str:
        if not self.resolved_path:
            return "No chat log file selected"
        if self.last_error:
            return f"{self.resolved_path}  ({self.last_error})"
        return f"{self.resolved_path}  ({self.lines_seen} lines read)"

    def available(self) -> bool:
        path = self.resolve_path()
        return bool(path) and os.path.isfile(path)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.resolved_path = self.resolve_path()
        if not self.resolved_path:
            raise StorageReadError(
                "Could not find a RAGE MP .storage file. Set the path in "
                "Settings > Chat log input (usually "
                r"C:\RAGEMP\client_resources\<hash>\.storage)."
            )
        if not os.path.isfile(self.resolved_path):
            raise StorageReadError(f"Chat log file not found: {self.resolved_path}")
        self._stop.clear()
        self._differ.reset()
        self._start_observer()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        obs, self._observer = self._observer, None
        if obs is not None:
            try:
                obs.stop()
                obs.join(timeout=2.0)
            except Exception:
                pass
        t, self._thread = self._thread, None
        if t is not None and t.is_alive():
            try:
                t.join(timeout=2.0)
            except Exception:
                pass

    def _start_observer(self) -> None:
        if not self.use_watchdog:
            self._log("Chat log: polling mode (watchdog disabled in settings).")
            return
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except Exception as exc:
            self._log(f"Chat log: watchdog unavailable ({exc}); falling back to polling.")
            return

        target = os.path.basename(self.resolved_path)
        wake = self._wake

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                for attr in ("src_path", "dest_path"):
                    p = getattr(event, attr, "") or ""
                    if p and os.path.basename(p) == target:
                        wake.set()
                        return

        try:
            obs = Observer()
            obs.schedule(_Handler(), os.path.dirname(self.resolved_path), recursive=False)
            obs.daemon = True
            obs.start()
            self._observer = obs
        except Exception as exc:
            self._log(f"Chat log: could not watch the folder ({exc}); falling back to polling.")

    def next_frames(self, timeout: float = 0.5) -> list:
        frames = []
        try:
            frames.append(self._frames.get(timeout=max(0.0, timeout)))
        except queue.Empty:
            return frames
        while True:
            try:
                frames.append(self._frames.get_nowait())
            except queue.Empty:
                break
        return frames

    def _emit(self, frame: list) -> None:
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            pass

    def _signature(self):
        try:
            st = os.stat(self.resolved_path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _drain_file(self, force: bool = False) -> None:
        sig = self._signature()
        if sig is None:
            self._note_error("file disappeared")
            return
        if not force and sig == self._last_sig:
            return
        self._last_sig = sig
        try:
            snapshot = read_chat_lines(
                self.resolved_path,
                encoding=self.encoding,
                attempts=self.retry_attempts,
                delay=self.retry_delay,
            )
        except StorageReadError as exc:
            self._note_error(str(exc))
            self._last_sig = None
            return
        self.last_error = ""
        self._err_logged = ""
        for line in self._differ.new_lines(snapshot):
            self.lines_seen += 1
            for frame in self._assembler.feed(line):
                self._emit(frame)

    def _note_error(self, msg: str) -> None:
        self.last_error = msg
        if msg != self._err_logged:
            self._err_logged = msg
            self._log(f"Chat log read problem (will keep retrying): {msg}")

    def _run(self) -> None:
        self._drain_file(force=True)
        while not self._stop.is_set():
            woken = self._wake.wait(self.poll_interval)
            if self._stop.is_set():
                break
            if woken:
                self._wake.clear()
                if self.debounce:
                    time.sleep(self.debounce)
            try:
                self._drain_file()
                for frame in self._assembler.flush_stale():
                    self._emit(frame)
            except Exception as exc:  # pragma: no cover - defensive
                self._note_error(str(exc))
