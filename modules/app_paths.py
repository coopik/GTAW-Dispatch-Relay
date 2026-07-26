from __future__ import annotations

import os
import shutil
import sys

APP_NAME = "911 Dispatch Relay"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> str:
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    return os.path.join(bundle_dir(), *parts)


def user_data_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def ensure_user_config(default_src: str) -> str:
    if not is_frozen():
        return default_src
    dest = os.path.join(user_data_dir(), "config.yaml")
    if not os.path.exists(dest):
        try:
            shutil.copyfile(default_src, dest)
        except Exception:
            return default_src
    return dest
