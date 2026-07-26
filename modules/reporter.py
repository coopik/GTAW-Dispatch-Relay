from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import threading
import time
import urllib.request
from collections import deque

_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|token|secret|password|authorization|bearer)\b"
    r"\s*[:=]\s*\S+"
)
_LONGKEY_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_TS_RE = re.compile(r"^\s*\[\d{1,2}:\d{2}(?::\d{2})?\]\s*")


def _redact(text: str) -> str:
    text = _SECRET_RE.sub(r"\1: [redacted]", text or "")
    text = _LONGKEY_RE.sub("[redacted]", text)
    return text.replace("```", "'''")


def _sanitize(text: str) -> str:
    text = (text or "")
    text = text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    text = re.sub(r"<@[!&]?\d+>", "[mention]", text)
    return text.replace("`", "'").replace("\n", " ").strip()


def _error_key(text: str) -> str:
    t = _TS_RE.sub("", text or "")
    t = re.sub(r"\d+", "#", t)
    return t.strip().lower()[:140]


class Reporter:
    def __init__(self, cfg: dict, app_version: str = "", log=None):
        cfg = cfg or {}
        self.webhook_url = str(cfg.get("webhook_url") or "").strip()
        self.enabled = bool(cfg.get("enabled", True))
        self.report_errors = bool(cfg.get("report_system_errors", True))
        self.app_version = str(app_version or "")
        self._log = log or (lambda *_a, **_k: None)

        self.user_cooldown = float(cfg.get("user_cooldown_sec", 60) or 0)
        self.error_cooldown = float(cfg.get("error_cooldown_sec", 120) or 0)
        self.max_per_hour = int(cfg.get("max_per_hour", 8) or 0)
        self.max_len = int(cfg.get("max_message_len", 1500) or 1500)

        self._last_user = 0.0
        self._error_last: dict[str, float] = {}
        self._recent_hashes: "deque[tuple[str, float]]" = deque(maxlen=80)
        self._sent_times: "deque[float]" = deque(maxlen=400)
        self._lock = threading.Lock()

    def configured(self) -> bool:
        return bool(
            self.enabled
            and self.webhook_url.startswith("https://")
            and "discord.com/api/webhooks/" in self.webhook_url
        )

    def _rate_ok(self, now: float) -> bool:
        while self._sent_times and now - self._sent_times[0] > 3600:
            self._sent_times.popleft()
        return self.max_per_hour <= 0 or len(self._sent_times) < self.max_per_hour

    def _is_dup(self, tag: str, text: str, now: float, window: float = 600.0) -> bool:
        h = hashlib.sha1((tag + "|" + text.strip().lower()).encode("utf-8", "ignore")).hexdigest()
        for hh, ts in self._recent_hashes:
            if hh == h and now - ts < window:
                return True
        self._recent_hashes.append((h, now))
        return False

    def report_bug(self, message: str, contact: str = "") -> tuple[bool, str]:
        message = (message or "").strip()
        if len(message) < 5:
            return False, "Please add a bit more detail before sending."
        if not self.configured():
            return self._save_locally(message, contact)
        now = time.time()
        with self._lock:
            if self.user_cooldown > 0 and now - self._last_user < self.user_cooldown:
                wait = int(self.user_cooldown - (now - self._last_user)) + 1
                return False, f"Please wait {wait}s before sending another report."
            if not self._rate_ok(now):
                return False, "Hourly report limit reached - please try again later."
            if self._is_dup("bug", message, now):
                return False, "That's identical to a report you just sent."
            self._last_user = now
            self._sent_times.append(now)
        extra = {}
        contact = _sanitize(contact)[:80]
        if contact:
            extra["Contact"] = contact
        content = self._format("\U0001F41E Bug report", message[: self.max_len], extra)
        self._send_async(content)
        return True, "Thanks! Your report was sent to the developer."

    def _save_locally(self, message: str, contact: str = "") -> tuple[bool, str]:
        try:
            from modules import app_paths

            folder = os.path.join(app_paths.user_data_dir(), "bug_reports")
            os.makedirs(folder, exist_ok=True)
            name = "bug-" + time.strftime("%Y%m%d-%H%M%S") + ".txt"
            path = os.path.join(folder, name)
            body = [
                "911 Dispatch Relay %s bug report" % (self.app_version or "?"),
                "When: " + time.strftime("%Y-%m-%d %H:%M:%S"),
                "System: %s %s" % (platform.system(), platform.release()),
                "Contact: " + (_sanitize(contact)[:80] or "(none given)"),
                "",
                _redact(message),
            ]
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(body))
        except Exception as exc:
            return False, "Direct sending is off and the report could not be saved: %s" % exc
        return True, ("Direct sending is not available on this build, so the report was saved "
                      "to %s - send it to the dev on Discord." % path)

    def report_error(self, text: str) -> None:
        if not (self.report_errors and self.configured()):
            return
        text = (text or "").strip()
        if not text:
            return
        now = time.time()
        key = _error_key(text)
        with self._lock:
            if self.error_cooldown > 0 and now - self._error_last.get(key, 0.0) < self.error_cooldown:
                return
            if not self._rate_ok(now):
                return
            if self._is_dup("err", key, now):
                return
            self._error_last[key] = now
            self._sent_times.append(now)
        content = self._format("\u26A0\uFE0F Auto-detected error", text[: self.max_len], None)
        self._send_async(content)

    def _format(self, title: str, body: str, extra: dict | None) -> str:
        head = (
            f"**{title}**  \u2022  v{self.app_version or '?'}  \u2022  "
            f"{platform.system()} {platform.release()}"
        )
        lines = [head, "```", _redact(body), "```"]
        if extra:
            for k, v in extra.items():
                lines.append(f"**{k}:** {_sanitize(str(v))}")
        return "\n".join(lines)

    def _send_async(self, content: str) -> None:
        threading.Thread(target=self._post, args=(content,), daemon=True).start()

    def _post(self, content: str) -> None:
        try:
            payload = json.dumps(
                {"content": content[:1900], "username": "Dispatch Relay Reporter"}
            ).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "911DispatchRelay",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:
            self._log(f"Report send failed: {e}")
