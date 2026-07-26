from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os


def _windows_monitors() -> list:
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

    monitors = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(RECT), ctypes.c_double,
    )

    def _cb(hmon, hdc, lprect, data):
        r = lprect.contents
        monitors.append({
            "left": int(r.left),
            "top": int(r.top),
            "width": int(r.right - r.left),
            "height": int(r.bottom - r.top),
        })
        return 1

    user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_cb), 0)
    monitors.sort(key=lambda m: (0 if (m["left"] == 0 and m["top"] == 0) else 1,
                                 m["left"], m["top"]))
    return monitors


def _fallback_monitors() -> list:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return [{"left": 0, "top": 0, "width": int(w), "height": int(h)}]
    except Exception:
        return [{"left": 0, "top": 0, "width": 1920, "height": 1080}]


def list_monitors() -> list:
    try:
        mons = _windows_monitors() if os.name == "nt" else _fallback_monitors()
    except Exception:
        mons = _fallback_monitors()
    if not mons:
        mons = _fallback_monitors()
    for i, m in enumerate(mons, start=1):
        m["index"] = i
    return mons


if __name__ == "__main__":  # pragma: no cover
    for mon in list_monitors():
        print(mon)
