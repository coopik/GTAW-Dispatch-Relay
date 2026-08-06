from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile

try:
    import requests
except Exception:
    requests = None

from modules import app_paths

_UA = "911DispatchRelay-Updater"
_VER_RE = re.compile(r"(\d+(?:\.\d+)*)")


def parse_version(text: str) -> tuple:
    m = _VER_RE.search(str(text or ""))
    if not m:
        return (0,)
    return tuple(int(p) for p in m.group(1).split("."))


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    n = max(len(r), len(l))
    r = r + (0,) * (n - len(r))
    l = l + (0,) * (n - len(l))
    return r > l


class UpdateInfo:
    def __init__(self, version="", url="", notes="", size=0, sha256="", page_url=""):
        self.version = str(version or "")
        self.url = str(url or "")
        self.notes = str(notes or "")
        self.size = int(size or 0)
        self.sha256 = str(sha256 or "").strip().lower()
        self.page_url = str(page_url or "")


class Updater:
    def __init__(self, cfg: dict, app_version: str = "", log=None):
        u = (cfg or {}).get("updates", {}) or {}
        self.enabled = bool(u.get("enabled", True))
        self.manifest_url = self.normalize_url(u.get("manifest_url", ""))
        self.check_on_start = bool(u.get("check_on_start", True))
        self.allow_prerelease = bool(u.get("allow_prerelease", False))
        self.timeout = float(u.get("timeout", 15) or 15)
        self.app_version = str(app_version or "")
        self._log = log or (lambda *_a, **_k: None)

    @staticmethod
    def normalize_url(url) -> str:
        """Accept a release API URL, a plain GitHub repo link, or owner/repo."""
        raw = str(url or "").strip().rstrip("/")
        if not raw:
            return ""
        if "api.github.com" in raw:
            return raw
        m = re.match(
            r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?(?:/.*)?$",
            raw,
            re.I,
        )
        if not m:
            m = re.match(r"^([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?$", raw)
        if m:
            return "https://api.github.com/repos/%s/%s/releases/latest" % (
                m.group(1),
                m.group(2),
            )
        return raw

    def configured(self) -> bool:
        return bool(self.enabled and requests is not None
                    and self.manifest_url.startswith("https://"))

    def can_install(self) -> bool:
        return bool(app_paths.is_frozen() and os.name == "nt")

    def check(self):
        if not self.configured():
            if requests is None:
                return False, None, "Update checks need the requests package."
            if not self.enabled:
                return False, None, "Update checks are turned off."
            return False, None, "No update source is configured."
        url = self.manifest_url
        try:
            if "api.github.com" in url and self.allow_prerelease:
                url = url.replace("/releases/latest", "/releases")
            resp = requests.get(url, timeout=self.timeout,
                                headers={"User-Agent": _UA,
                                         "Accept": "application/vnd.github+json"})
            if resp.status_code == 404:
                return False, None, "No releases published yet."
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return False, None, "Could not reach the update server: %s" % exc
        try:
            info = self._parse(data)
        except Exception as exc:
            return False, None, "Update information could not be read: %s" % exc
        if info is None:
            return False, None, "No installer was published with the latest release."
        if is_newer(info.version, self.app_version) and not info.url:
            return True, info, ("Version %s is available, but that release has no "
                                "installer attached - open the release page to get it."
                                % info.version)
        if not is_newer(info.version, self.app_version):
            return False, info, "You are up to date."
        return True, info, "Version %s is available." % info.version

    def _parse(self, data):
        if isinstance(data, list):
            data = next((r for r in data if not r.get("draft")), None)
            if data is None:
                return None
        if "tag_name" in data or "assets" in data:
            version = data.get("tag_name") or data.get("name") or ""
            asset = None
            for a in data.get("assets") or []:
                name = str(a.get("name", "")).lower()
                if name.endswith(".exe") and "setup" in name:
                    asset = a
                    break
            if asset is None:
                for a in data.get("assets") or []:
                    if str(a.get("name", "")).lower().endswith(".exe"):
                        asset = a
                        break
            if asset is None:
                return UpdateInfo(version=version,
                                  notes=data.get("body", ""),
                                  page_url=data.get("html_url", ""))
            return UpdateInfo(version=version,
                              url=asset.get("browser_download_url", ""),
                              notes=data.get("body", ""),
                              size=asset.get("size", 0),
                              page_url=data.get("html_url", ""))
        return UpdateInfo(version=data.get("version", ""),
                          url=data.get("url", "") or data.get("installer", ""),
                          notes=data.get("notes", "") or data.get("changelog", ""),
                          size=data.get("size", 0),
                          sha256=data.get("sha256", ""),
                          page_url=data.get("page", ""))

    def download(self, info: UpdateInfo, progress=None):
        if requests is None:
            return False, "Downloading needs the requests package."
        if not (info and info.url.startswith("https://")):
            return False, "That release has no valid download link."
        name = os.path.basename(info.url.split("?")[0]) or "update.exe"
        if not name.lower().endswith(".exe"):
            return False, "The published update is not an installer."
        folder = os.path.join(app_paths.user_data_dir(), "updates")
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            folder = tempfile.gettempdir()
        path = os.path.join(folder, name)
        tmp = path + ".part"
        digest = hashlib.sha256()
        try:
            with requests.get(info.url, timeout=self.timeout, stream=True,
                              headers={"User-Agent": _UA}) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length") or info.size or 0)
                done = 0
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=262144):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if progress and total > 0:
                            progress(min(1.0, done / float(total)))
        except Exception as exc:
            try:
                os.remove(tmp)
            except Exception:
                pass
            return False, "Download failed: %s" % exc
        if info.sha256 and digest.hexdigest().lower() != info.sha256:
            try:
                os.remove(tmp)
            except Exception:
                pass
            return False, "The download did not match its checksum and was discarded."
        try:
            if os.path.exists(path):
                os.remove(path)
            os.replace(tmp, path)
        except Exception as exc:
            return False, "Could not save the installer: %s" % exc
        return True, path

    def install(self, setup_path: str):
        if not os.path.exists(setup_path):
            return False, "The downloaded installer is missing."
        if not self.can_install():
            return False, ("Automatic install only works in the installed Windows build. "
                           "The installer was saved to %s - run it yourself." % setup_path)
        exe = sys.executable
        # The app has to be gone before the installer can replace its files, so the
        # sequence is handed to a detached script: wait, install silently, relaunch.
        script = (
            "@echo off\r\n"
            "ping -n 4 127.0.0.1 >nul\r\n"
            'start "" /wait "%s" /SILENT /SUPPRESSMSGBOXES /NOCANCEL /NORESTART /CLOSEAPPLICATIONS\r\n'
            'start "" "%s"\r\n'
            'del "%%~f0"\r\n'
        ) % (setup_path, exe)
        try:
            folder = os.path.join(app_paths.user_data_dir(), "updates")
            os.makedirs(folder, exist_ok=True)
            cmd_path = os.path.join(folder, "apply_update.cmd")
            with open(cmd_path, "w", encoding="ascii", errors="ignore") as fh:
                fh.write(script)
            flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
            subprocess.Popen(["cmd.exe", "/c", cmd_path], creationflags=flags,
                             close_fds=True, cwd=folder)
        except Exception as exc:
            return False, "Could not start the installer: %s" % exc
        return True, "Installing the update. The app will close and reopen on its own."
