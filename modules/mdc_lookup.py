from __future__ import annotations

import logging
import os
import queue
import threading
import time
from logging.handlers import RotatingFileHandler
from urllib.parse import quote

from modules import app_paths
from modules.mdc_auth import MDCSession
from modules import mdc_parser


class MDCManager:
    def __init__(self, cfg: dict | None = None, llm=None, log=None, speak=None):
        cfg = cfg or {}
        self.cfg = cfg
        self.enabled = bool(cfg.get("enabled", False))
        self.llm = llm
        self._log = log or (lambda *_a, **_k: None)
        self._speak = speak or (lambda *a, **k: None)
        self.session = MDCSession(cfg, log=self._log)

        self.cooldown = max(1.0, float(cfg.get("cooldown_sec", 8) or 8))
        self.max_queue = max(1, int(cfg.get("max_queue", 5) or 5))
        self.timeout = int(cfg.get("timeout", 15) or 15)
        self.channel = str(cfg.get("response_channel") or "").strip()
        self.standby_ack = bool(cfg.get("standby_ack", True))
        self.name_url = str(cfg.get("name_search_url") or "").strip()
        self.plate_url = str(cfg.get("plate_search_url") or "").strip()
        self.selectors = cfg.get("selectors", {}) or {}
        self.ai_read_page = bool(cfg.get("ai_read_page", True))
        self.render_page = bool(cfg.get("render_page", True))
        self.login_markers = [
            str(m).lower() for m in (cfg.get("login_markers") or [])
        ] or None
        self.user_agent = str(
            cfg.get("user_agent")
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) 911DispatchRelay MDC"
        )

        self._q: "queue.Queue" = queue.Queue(maxsize=self.max_queue)
        self._last_req = 0.0
        self._backoff = 0.0
        self._session_ok = True
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._logger = self._make_logger()
        if self.enabled:
            self._start_worker()

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "logged_in": self.session.has_session(),
            "encryption": self.session.encryption_available(),
            "session_ok": self._session_ok,
        }

    def status_text(self) -> str:
        if not self.session.encryption_available():
            return "Secure storage unavailable on this system"
        if not self.session.has_session():
            return "Not logged in"
        if not self._session_ok:
            return "Session expired - please log in again"
        return "Logged in"

    def _make_logger(self) -> logging.Logger:
        lg = logging.getLogger("mdc_requests")
        lg.setLevel(logging.INFO)
        lg.propagate = False
        if not lg.handlers:
            try:
                path = os.path.join(app_paths.user_data_dir(), "mdc_requests.log")
                h = RotatingFileHandler(path, maxBytes=256 * 1024, backupCount=3, encoding="utf-8")
                h.setFormatter(logging.Formatter("%(asctime)s\t%(message)s"))
                lg.addHandler(h)
            except Exception:
                lg.addHandler(logging.NullHandler())
        return lg

    def _start_worker(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except Exception:
            pass

    def handle(self, flag: dict) -> None:
        if not self.enabled:
            return
        if not self.session.encryption_available():
            self._log("MDC: secure storage unavailable; lookup skipped.")
            return
        if not self.session.has_session():
            self._log("MDC: not logged in - use Settings > MDC Lookup > Login. Lookup skipped.")
            return
        target = str(flag.get("target") or "").strip()
        if not target:
            return
        try:
            self._q.put_nowait(flag)
        except queue.Full:
            self._log("MDC: request queue full - dropped a lookup (rate limit protection).")
            return
        if self.standby_ack:
            self._speak_standby(flag.get("callsign"))

    def _speak_standby(self, callsign) -> None:
        cs = ""
        try:
            from modules import llm as _llm
            cs = _llm._phon_cs(callsign) if callsign else ""
        except Exception:
            cs = str(callsign or "")
        phrase = f"Copy {cs}, standby." if cs else "Copy, standby."
        summary = f"[MDC standby] {callsign or 'unit'}"
        try:
            self._speak(phrase, summary)
        except Exception as e:
            self._log(f"MDC: could not queue standby ({e})")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                flag = self._q.get()
            except Exception:
                continue
            if flag is None:
                break
            try:
                self._respect_rate_limit()
                self._process(flag)
            except Exception as e:
                self._log(f"MDC lookup error: {e}")
            finally:
                try:
                    self._q.task_done()
                except Exception:
                    pass

    def _respect_rate_limit(self) -> None:
        wait = self.cooldown + self._backoff - (time.monotonic() - self._last_req)
        while wait > 0 and not self._stop.is_set():
            time.sleep(min(wait, 0.5))
            wait = self.cooldown + self._backoff - (time.monotonic() - self._last_req)

    def _process(self, flag: dict) -> None:
        lookup = flag.get("lookup")
        target = str(flag.get("target") or "").strip()
        callsign = flag.get("callsign")
        self._logger.info(f"{lookup}\t{target}\t{callsign or '-'}")
        self._log(f"MDC: looking up {lookup} '{target}' for {callsign or 'unit'}.")

        url = self.plate_url if lookup == "plate" else self.name_url
        if not url:
            self._log(f"MDC: no {lookup} search URL configured (mdc_lookup.*_search_url).")
            return

        self._last_req = time.monotonic()
        try:
            html, final_url, code = self._fetch(url, target)
        except Exception as e:
            self._backoff = min(60.0, (self._backoff or self.cooldown) * 2)
            self._log(f"MDC: request failed ({e}); backing off {self._backoff:.0f}s.")
            return

        if code in (401, 403) or code == 429:
            if code == 429:
                self._backoff = min(120.0, (self._backoff or self.cooldown) * 2)
                self._log(f"MDC: rate-limited by server (429); backing off {self._backoff:.0f}s.")
                return
            self._session_expired()
            return
        if code and code >= 500:
            self._backoff = min(120.0, (self._backoff or self.cooldown) * 2)
            self._log(f"MDC: server error {code}; backing off {self._backoff:.0f}s.")
            return
        if mdc_parser.looks_like_login(html, self.login_markers) or "login" in (final_url or "").lower():
            self._session_expired()
            return

        self._backoff = 0.0
        self._session_ok = True

        # the fallback when there's no API key or the AI path yields nothing.
        phrase = ""
        result = {"lookup": lookup, "target": target, "found": True}
        if self.ai_read_page and self.llm is not None and getattr(self.llm, "has_api", None) and self.llm.has_api():
            try:
                page_text = mdc_parser.visible_text(html)
                phrase = self.llm.mdc_response_from_page(
                    page_text, lookup, target, callsign, acknowledged=self.standby_ack
                ) or ""
                if phrase:
                    self._log("MDC: AI read the record page directly.")
            except Exception as e:
                self._log(f"MDC: AI page read failed, using parser ({e})")
                phrase = ""

        if not phrase:
            if lookup == "plate":
                result = mdc_parser.parse_plate_result(html, self.selectors.get("plate"))
            else:
                result = mdc_parser.parse_name_result(html, self.selectors.get("name"))
            result["target"] = target
            phrase = self._to_phrase(result, callsign, acknowledged=self.standby_ack)

        if not phrase:
            return
        if self.channel:
            phrase = f"{self.channel}. {phrase}" if not phrase.startswith(self.channel) else phrase
        summary = self._summary(result, callsign)
        try:
            self._speak(phrase, summary, alert=not self.standby_ack)
        except TypeError:
            self._speak(phrase, summary)
        except Exception as e:
            self._log(f"MDC: could not queue audio ({e})")

    def _fetch(self, url_template: str, target: str):
        q = quote(target)
        url = url_template.replace("{q}", q) if "{q}" in url_template else (url_template + q)
        if self.render_page:
            rendered = self._render(url)
            if rendered is not None:
                return rendered
        return self._fetch_requests(url)

    def _fetch_requests(self, url: str):
        import requests

        cookies = self.session.cookie_dict()
        resp = requests.get(
            url,
            cookies=cookies,
            headers={"User-Agent": self.user_agent, "Accept": "text/html"},
            timeout=self.timeout,
            allow_redirects=True,
        )
        return resp.text, str(resp.url), int(resp.status_code)

    def _render(self, url: str):
        try:
            from modules import mdc_auth
            if not mdc_auth.playwright_available():
                return None
            from playwright.sync_api import sync_playwright
            profile = mdc_auth.profile_dir()
            ms = int(max(5, self.timeout) * 1000)
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(profile, headless=True)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.set_default_timeout(ms)
                    page.goto(url, wait_until="networkidle", timeout=ms)
                    try:
                        page.wait_for_timeout(1200)
                    except Exception:
                        pass
                    return page.content(), str(page.url), 200
                finally:
                    context.close()
        except Exception as e:
            self._log(f"MDC: page render unavailable, using direct request ({e})")
            return None

    def _session_expired(self) -> None:
        self._session_ok = False
        self._log("Web MDC session expired - please log in again (Settings > MDC Lookup).")

    def _to_phrase(self, result: dict, callsign, acknowledged=False) -> str:
        phrase = ""
        try:
            if self.llm is not None and getattr(self.llm, "mdc_response", None):
                phrase = self.llm.mdc_response(result, callsign, acknowledged=acknowledged) or ""
        except Exception as e:
            self._log(f"MDC: AI summary failed, using offline generator ({e})")
            phrase = ""
        if not phrase:
            try:
                from modules import llm as _llm
                phrase = _llm.build_mdc_response(result, callsign, acknowledged=acknowledged)
            except Exception as e:
                self._log(f"MDC: could not build response ({e})")
                return ""
        if self.channel and phrase:
            phrase = f"{self.channel}. {phrase}"
        return phrase

    @staticmethod
    def _summary(result: dict, callsign) -> str:
        who = callsign or "unit"
        tgt = result.get("target") or ""
        return f"[MDC {result.get('lookup', '?')}] {who}: {tgt}"
