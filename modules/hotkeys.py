from __future__ import annotations

try:
    import keyboard  # type: ignore
except Exception:
    keyboard = None


class HotkeyManager:
    def __init__(self, on_start, on_stop, log=None):
        self._on_start = on_start
        self._on_stop = on_stop
        self._log = log or (lambda msg: None)
        self._registered = []
        self._warned = False

    def available(self) -> bool:
        return keyboard is not None

    def apply(self, start_key: str = "", stop_key: str = "", enabled: bool = True) -> None:
        self.clear()
        if not enabled:
            return
        if not (start_key or stop_key):
            return
        if keyboard is None:
            if not self._warned:
                self._log("Global hotkeys need the 'keyboard' package (pip install keyboard).")
                self._warned = True
            return
        if start_key:
            self._register(start_key, self._on_start, "Start")
        if stop_key:
            self._register(stop_key, self._on_stop, "Stop")

    def _register(self, key: str, callback, label: str) -> None:
        try:
            handle = keyboard.add_hotkey(key, lambda: self._safe(callback, label))
            self._registered.append(handle)
            self._log(f"Bound {label} hotkey to '{key}'.")
        except Exception as exc:
            self._log(f"Could not bind {label} hotkey '{key}': {exc}")

    def _safe(self, callback, label: str) -> None:
        try:
            callback()
        except Exception as exc:
            self._log(f"{label} hotkey error: {exc}")

    def clear(self) -> None:
        if keyboard is None:
            self._registered = []
            return
        for handle in self._registered:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._registered = []

    def stop(self) -> None:
        self.clear()
