from __future__ import annotations

import math
import os

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL = True
except Exception:
    _PIL = False

try:
    import customtkinter as ctk
except Exception:
    ctk = None

_SS = 4
_cache: dict = {}

_HERE = os.path.dirname(os.path.abspath(__file__))
_FA_PATH = os.path.join(os.path.dirname(_HERE), "assets", "fonts", "fa-solid-900.ttf")

_FA_GLYPHS = {
    "dashboard": "\uf625",
    "settings": "\uf013",
    "info": "\uf05a",
    "play": "\uf04b",
    "stop": "\uf04d",
    "mic": "\uf130",
    "target": "\uf05b",
    "save": "\uf0c7",
    "monitor": "\uf108",
    "scan": "\uf15c",
    "chip": "\uf2db",
    "flag": "\uf024",
    "radio": "\uf519",
    "volume": "\uf028",
    "bell": "\uf0f3",
    "shield": "\uf3ed",
    "pin": "\uf3c5",
    "siren": "\uf132",
    "reload": "\uf021",
    "book": "\uf02d",
    "search": "\uf002",
    "sun": "\uf185",
    "moon": "\uf186",
}


def _new(size):
    s = size * _SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), s


def _finish(img, size):
    return img.resize((size, size), Image.LANCZOS)


def _star(dr, cx, cy, ro, ri, c):
    pts = []
    for i in range(10):
        r = ro if i % 2 == 0 else ri
        a = math.radians(-90 + i * 36)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    dr.polygon(pts, fill=c)


def _d_dashboard(dr, s, c):
    lw = max(2, int(s * 0.075))
    m = s * 0.16
    bbox = [m, m * 1.5, s - m, s - m * 0.2]
    dr.arc(bbox, start=180, end=360, fill=c, width=lw)
    cx = s / 2
    cy = (bbox[1] + bbox[3]) / 2
    r = (s - 2 * m) * 0.42
    a = math.radians(315)
    dr.line([cx, cy, cx + r * math.cos(a), cy + r * math.sin(a)], fill=c, width=lw)
    dr.ellipse([cx - lw, cy - lw, cx + lw, cy + lw], fill=c)


def _d_settings(dr, s, c):
    cx = cy = s / 2
    R = s * 0.32
    r = s * 0.21
    lw = max(2, int(s * 0.07))
    for k in range(8):
        a = math.radians(k * 45)
        x0 = cx + r * math.cos(a)
        y0 = cy + r * math.sin(a)
        x1 = cx + R * math.cos(a)
        y1 = cy + R * math.sin(a)
        dr.line([x0, y0, x1, y1], fill=c, width=int(lw * 1.7))
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=lw)
    ih = s * 0.09
    dr.ellipse([cx - ih, cy - ih, cx + ih, cy + ih], outline=c, width=lw)


def _d_info(dr, s, c):
    lw = max(2, int(s * 0.07))
    m = s * 0.16
    dr.ellipse([m, m, s - m, s - m], outline=c, width=lw)
    cx = s / 2
    d = lw * 0.8
    dr.ellipse([cx - d, s * 0.30 - d, cx + d, s * 0.30 + d], fill=c)
    dr.line([cx, s * 0.44, cx, s * 0.72], fill=c, width=int(lw * 1.4))


def _d_play(dr, s, c):
    m = s * 0.28
    dr.polygon([(m, s * 0.22), (m, s * 0.78), (s - m * 0.9, s / 2)], fill=c)


def _d_stop(dr, s, c):
    m = s * 0.30
    dr.rounded_rectangle([m, m, s - m, s - m], radius=s * 0.06, fill=c)


def _d_mic(dr, s, c):
    lw = max(2, int(s * 0.07))
    cx = s / 2
    w = s * 0.16
    top = s * 0.16
    bot = s * 0.52
    dr.rounded_rectangle([cx - w, top, cx + w, bot], radius=w, fill=c)
    dr.arc([cx - w * 1.9, top + s * 0.10, cx + w * 1.9, bot + s * 0.06],
           start=20, end=160, fill=c, width=lw)
    dr.line([cx, bot + s * 0.06, cx, s * 0.80], fill=c, width=lw)
    dr.line([cx - s * 0.12, s * 0.80, cx + s * 0.12, s * 0.80], fill=c, width=lw)


def _d_target(dr, s, c):
    lw = max(2, int(s * 0.07))
    m = s * 0.18
    dr.ellipse([m, m, s - m, s - m], outline=c, width=lw)
    cx = cy = s / 2
    dr.line([cx, s * 0.06, cx, s * 0.30], fill=c, width=lw)
    dr.line([cx, s * 0.70, cx, s * 0.94], fill=c, width=lw)
    dr.line([s * 0.06, cy, s * 0.30, cy], fill=c, width=lw)
    dr.line([s * 0.70, cy, s * 0.94, cy], fill=c, width=lw)
    dr.ellipse([cx - lw, cy - lw, cx + lw, cy + lw], fill=c)


def _d_save(dr, s, c):
    lw = max(2, int(s * 0.06))
    m = s * 0.16
    dr.rounded_rectangle([m, m, s - m, s - m], radius=s * 0.05, outline=c, width=lw)
    dr.rectangle([s * 0.34, m, s * 0.66, s * 0.34], outline=c, width=lw)
    dr.rectangle([s * 0.30, s * 0.52, s * 0.70, s - m], outline=c, width=lw)


def _d_monitor(dr, s, c):
    lw = max(2, int(s * 0.07))
    dr.rounded_rectangle([s * 0.14, s * 0.18, s * 0.86, s * 0.62],
                         radius=s * 0.05, outline=c, width=lw)
    dr.line([s * 0.5, s * 0.62, s * 0.5, s * 0.78], fill=c, width=lw)
    dr.line([s * 0.34, s * 0.80, s * 0.66, s * 0.80], fill=c, width=int(lw * 1.2))


def _d_scan(dr, s, c):
    lw = max(2, int(s * 0.06))
    dr.rounded_rectangle([s * 0.24, s * 0.14, s * 0.76, s * 0.86],
                         radius=s * 0.05, outline=c, width=lw)
    for i, y in enumerate([0.30, 0.42, 0.54, 0.66]):
        x1 = s * 0.66 if i % 2 == 0 else s * 0.58
        dr.line([s * 0.34, s * y, x1, s * y], fill=c, width=int(lw * 0.9))


def _d_chip(dr, s, c):
    lw = max(2, int(s * 0.07))
    dr.rounded_rectangle([s * 0.26, s * 0.26, s * 0.74, s * 0.74],
                         radius=s * 0.04, outline=c, width=lw)
    dr.rounded_rectangle([s * 0.38, s * 0.38, s * 0.62, s * 0.62],
                         radius=s * 0.02, outline=c, width=lw)
    for t in [0.36, 0.5, 0.64]:
        dr.line([s * t, s * 0.12, s * t, s * 0.26], fill=c, width=lw)
        dr.line([s * t, s * 0.74, s * t, s * 0.88], fill=c, width=lw)
        dr.line([s * 0.12, s * t, s * 0.26, s * t], fill=c, width=lw)
        dr.line([s * 0.74, s * t, s * 0.88, s * t], fill=c, width=lw)


def _d_flag(dr, s, c):
    lw = max(2, int(s * 0.075))
    dr.line([s * 0.30, s * 0.12, s * 0.30, s * 0.88], fill=c, width=lw)
    dr.polygon([(s * 0.30, s * 0.16), (s * 0.78, s * 0.28), (s * 0.30, s * 0.44)], fill=c)


def _d_radio(dr, s, c):
    lw = max(2, int(s * 0.07))
    cx = cy = s / 2
    dr.ellipse([cx - s * 0.06, cy - s * 0.06, cx + s * 0.06, cy + s * 0.06], fill=c)
    for rr in [0.18, 0.30]:
        r = s * rr
        box = [cx - r, cy - r, cx + r, cy + r]
        dr.arc(box, start=300, end=60, fill=c, width=lw)
        dr.arc(box, start=120, end=240, fill=c, width=lw)


def _d_volume(dr, s, c):
    lw = max(2, int(s * 0.07))
    dr.polygon([(s * 0.20, s * 0.40), (s * 0.34, s * 0.40), (s * 0.48, s * 0.26),
                (s * 0.48, s * 0.74), (s * 0.34, s * 0.60), (s * 0.20, s * 0.60)], fill=c)
    dr.arc([s * 0.42, s * 0.30, s * 0.78, s * 0.70], start=300, end=60, fill=c, width=lw)
    dr.arc([s * 0.50, s * 0.36, s * 0.70, s * 0.64], start=300, end=60, fill=c, width=lw)


def _d_bell(dr, s, c):
    lw = max(2, int(s * 0.07))
    dr.arc([s * 0.30, s * 0.18, s * 0.70, s * 0.62], start=180, end=360, fill=c, width=lw)
    dr.line([s * 0.30, s * 0.40, s * 0.26, s * 0.66], fill=c, width=lw)
    dr.line([s * 0.70, s * 0.40, s * 0.74, s * 0.66], fill=c, width=lw)
    dr.line([s * 0.24, s * 0.66, s * 0.76, s * 0.66], fill=c, width=lw)
    dr.ellipse([s * 0.46, s * 0.68, s * 0.54, s * 0.80], fill=c)


def _d_shield(dr, s, c):
    lw = max(2, int(s * 0.07))
    pts = [(s * 0.5, s * 0.14), (s * 0.80, s * 0.26), (s * 0.80, s * 0.52),
           (s * 0.5, s * 0.86), (s * 0.20, s * 0.52), (s * 0.20, s * 0.26)]
    dr.line(pts + [pts[0]], fill=c, width=lw, joint="curve")
    _star(dr, s * 0.5, s * 0.45, s * 0.15, s * 0.06, c)


def _d_pin(dr, s, c):
    cx = s / 2
    top = s * 0.12
    R = s * 0.22
    dr.pieslice([cx - R, top, cx + R, top + 2 * R], start=0, end=360, fill=c)
    dr.polygon([(cx - R * 0.7, top + R * 1.35), (cx + R * 0.7, top + R * 1.35),
                (cx, s * 0.90)], fill=c)


def _d_siren(dr, s, c):
    lw = max(2, int(s * 0.07))
    dr.pieslice([s * 0.30, s * 0.30, s * 0.70, s * 0.70], start=180, end=360, fill=c)
    dr.rounded_rectangle([s * 0.26, s * 0.64, s * 0.74, s * 0.77], radius=s * 0.02, fill=c)
    dr.line([s * 0.5, s * 0.12, s * 0.5, s * 0.26], fill=c, width=lw)
    dr.line([s * 0.20, s * 0.22, s * 0.30, s * 0.34], fill=c, width=lw)
    dr.line([s * 0.80, s * 0.22, s * 0.70, s * 0.34], fill=c, width=lw)


def _d_reload(dr, s, c):
    lw = max(2, int(s * 0.08))
    m = s * 0.22
    dr.arc([m, m, s - m, s - m], start=60, end=330, fill=c, width=lw)
    ax, ay = s * 0.74, s * 0.30
    dr.polygon([(ax, ay - s * 0.02), (ax + s * 0.12, ay + s * 0.02),
                (ax + s * 0.02, ay + s * 0.14)], fill=c)


def _d_book(dr, s, c):
    lw = max(2, int(s * 0.07))
    dr.rounded_rectangle([s * 0.22, s * 0.16, s * 0.78, s * 0.84],
                         radius=s * 0.05, outline=c, width=lw)
    dr.line([s * 0.5, s * 0.16, s * 0.5, s * 0.84], fill=c, width=lw)
    for y in (0.34, 0.5, 0.66):
        dr.line([s * 0.30, s * y, s * 0.45, s * y], fill=c, width=max(2, int(lw * 0.8)))
        dr.line([s * 0.55, s * y, s * 0.70, s * y], fill=c, width=max(2, int(lw * 0.8)))


def _d_search(dr, s, c):
    lw = max(2, int(s * 0.08))
    r = s * 0.24
    cx = cy = s * 0.42
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=lw)
    dr.line([cx + r * 0.72, cy + r * 0.72, s * 0.84, s * 0.84], fill=c,
            width=int(lw * 1.25))


def _d_sun(dr, s, c):
    lw = max(2, int(s * 0.07))
    cx = cy = s / 2
    r = s * 0.15
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=lw)
    for k in range(8):
        a = math.radians(k * 45)
        x0 = cx + (r + s * 0.07) * math.cos(a)
        y0 = cy + (r + s * 0.07) * math.sin(a)
        x1 = cx + (r + s * 0.17) * math.cos(a)
        y1 = cy + (r + s * 0.17) * math.sin(a)
        dr.line([x0, y0, x1, y1], fill=c, width=lw)


def _d_moon(dr, s, c):
    r = s * 0.30
    cx = cy = s / 2
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    ox, oy = cx + r * 0.55, cy - r * 0.15
    dr.ellipse([ox - r, oy - r, ox + r, oy + r], fill=(0, 0, 0, 0))


_DRAW = {
    "dashboard": _d_dashboard, "settings": _d_settings, "info": _d_info,
    "play": _d_play, "stop": _d_stop, "mic": _d_mic, "target": _d_target,
    "save": _d_save, "monitor": _d_monitor, "scan": _d_scan, "chip": _d_chip,
    "flag": _d_flag, "radio": _d_radio, "volume": _d_volume, "bell": _d_bell,
    "shield": _d_shield, "pin": _d_pin, "siren": _d_siren, "reload": _d_reload,
    "book": _d_book, "search": _d_search, "sun": _d_sun, "moon": _d_moon,
}


def _fa_icon(name, size, color):
    if not os.path.exists(_FA_PATH):
        return None
    glyph = _FA_GLYPHS.get(name)
    if not glyph:
        return None
    try:
        img, dr, s = _new(size)
        font = ImageFont.truetype(_FA_PATH, int(s * 0.78))
        bbox = dr.textbbox((0, 0), glyph, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        dr.text(((s - w) / 2 - bbox[0], (s - h) / 2 - bbox[1]), glyph,
                font=font, fill=color)
        return _finish(img, size)
    except Exception:
        return None


def _pil_icon(name, size, color):
    fn = _DRAW.get(name, _d_info)
    img, dr, s = _new(size)
    fn(dr, s, color)
    return _finish(img, size)


def get_ctk_image(name, size=18, color="#334155", dark_color=None):
    if not _PIL or ctk is None:
        return None
    if dark_color is None:
        dark_color = color
    key = (name, size, color, dark_color)
    if key in _cache:
        return _cache[key]
    image = None
    try:
        light_pil = _fa_icon(name, size, color) or _pil_icon(name, size, color)
        dark_pil = _fa_icon(name, size, dark_color) or _pil_icon(name, size, dark_color)
        image = ctk.CTkImage(light_image=light_pil, dark_image=dark_pil, size=(size, size))
    except Exception:
        image = None
    _cache[key] = image
    return image
