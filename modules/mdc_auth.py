from __future__ import annotations

import json
import os
import time

from modules import app_paths

SESSION_FILENAME = "mdc_session.bin"
PROFILE_DIRNAME = "mdc_browser_profile"


def session_path() -> str:
    return os.path.join(app_paths.user_data_dir(), SESSION_FILENAME)


def profile_dir() -> str:
    d = os.path.join(app_paths.user_data_dir(), PROFILE_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


def dpapi_available() -> bool:
    if os.name != "nt":
        return False
    try:
        import win32crypt  # noqa: F401
        return True
    except Exception:
        return False


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def _encrypt(data: bytes) -> bytes | None:
    try:
        import win32crypt
        blob = win32crypt.CryptProtectData(
            data, "911DispatchRelay MDC session", None, None, None, 0
        )
        return bytes(blob)
    except Exception:
        return None


def _decrypt(blob: bytes) -> bytes | None:
    try:
        import win32crypt
        res = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
        return bytes(res[1])
    except Exception:
        return None


class MDCSession:
    def __init__(self, cfg: dict | None = None, log=None):
        self.cfg = cfg or {}
        self._log = log or (lambda *_a, **_k: None)
        self.path = session_path()

    def encryption_available(self) -> bool:
        return dpapi_available()

    def has_session(self) -> bool:
        return os.path.exists(self.path)

    def load_cookies(self) -> list[dict] | None:
        if not self.has_session():
            return None
        try:
            with open(self.path, "rb") as f:
                blob = f.read()
        except Exception as e:
            self._log(f"MDC: could not read stored session ({e})")
            return None
        raw = _decrypt(blob)
        if raw is None:
            self._log(
                "MDC: could not decrypt the stored session "
                "(different Windows user or corrupt file). Please log in again."
            )
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
            return payload.get("cookies") or None
        except Exception:
            return None

    def cookie_dict(self) -> dict:
        cookies = self.load_cookies() or []
        return {
            c.get("name"): c.get("value")
            for c in cookies
            if c.get("name") is not None
        }

    def saved_at(self) -> float | None:
        if not self.has_session():
            return None
        try:
            with open(self.path, "rb") as f:
                raw = _decrypt(f.read())
            if raw is None:
                return None
            return float(json.loads(raw.decode("utf-8")).get("saved") or 0) or None
        except Exception:
            return None

    def save_cookies(self, cookies: list[dict]) -> tuple[bool, str]:
        if not self.encryption_available():
            return False, (
                "Secure storage (Windows DPAPI) is unavailable, so the session "
                "was NOT stored (never written in plaintext)."
            )
        payload = json.dumps({"cookies": cookies, "saved": time.time()}).encode("utf-8")
        blob = _encrypt(payload)
        if blob is None:
            return False, "Could not encrypt the session."
        try:
            with open(self.path, "wb") as f:
                f.write(blob)
            try:
                os.chmod(self.path, 0o600)
            except Exception:
                pass
        except Exception as e:
            return False, f"Could not write the session file ({e})."
        return True, "Web MDC session stored (encrypted)."

    def clear(self) -> tuple[bool, str]:
        removed = False
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
                removed = True
        except Exception as e:
            return False, f"Could not delete the session ({e})."
        return True, "Logged out - stored session cleared." if removed else "No session to clear."


def login_interactive(cfg: dict, log=None) -> tuple[bool, str]:
    log = log or (lambda *_a, **_k: None)
    cfg = cfg or {}
    login_url = str(cfg.get("login_url") or "").strip()
    if not login_url:
        return False, (
            "No Web MDC login URL configured. Set mdc_lookup.login_url in config.yaml first."
        )
    session = MDCSession(cfg, log=log)
    if not session.encryption_available():
        return False, (
            "Secure storage (Windows DPAPI) is unavailable on this system, so "
            "login is disabled (we never store a session in plaintext)."
        )
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False, (
            "Playwright isn't installed. Run:  py -m pip install playwright  "
            "then  py -m playwright install chromium"
        )

    pdir = profile_dir()
    log("MDC: opening a browser window - log in normally, then close the window when done.")
    cookies: list[dict] = []
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                pdir,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            while True:
                try:
                    if not context.pages:
                        break
                    cookies = context.cookies()
                except Exception:
                    break
                time.sleep(1.0)
            try:
                context.close()
            except Exception:
                pass
    except Exception as e:
        return False, f"Browser login failed: {e}"

    if not cookies:
        return False, "No session cookies were captured. Please try logging in again."
    ok, msg = session.save_cookies(cookies)
    if ok:
        log("MDC: session captured and stored (encrypted).")
    else:
        log(f"MDC: {msg}")
    return ok, msg
