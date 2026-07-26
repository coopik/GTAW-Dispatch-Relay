from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "app.ico")
BASE = 256
PRIMARY = (37, 99, 235)
PRIMARY_DK = (29, 78, 216)
WHITE = (255, 255, 255)
RED = (220, 38, 38)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial_Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render(size: int) -> Image.Image:
    s = BASE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    grad = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        r = int(PRIMARY[0] + (PRIMARY_DK[0] - PRIMARY[0]) * t)
        g = int(PRIMARY[1] + (PRIMARY_DK[1] - PRIMARY[1]) * t)
        b = int(PRIMARY[2] + (PRIMARY_DK[2] - PRIMARY[2]) * t)
        gd.line([(0, y), (s, y)], fill=(r, g, b, 255))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=54, fill=255)
    img.paste(grad, (0, 0), mask)

    cx = s // 2
    dome_w, dome_h = 70, 40
    dome_box = [cx - dome_w // 2, 40, cx + dome_w // 2, 40 + dome_h]
    d.pieslice(dome_box, start=180, end=360, fill=RED)
    d.rectangle([cx - dome_w // 2, 58, cx + dome_w // 2, 66], fill=(120, 15, 15, 255))

    f = _font(118)
    text = "911"
    bbox = d.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((cx - tw / 2 - bbox[0], 96 - bbox[1]), text, font=f, fill=WHITE)

    f2 = _font(30)
    label = "DISPATCH"
    b2 = d.textbbox((0, 0), label, font=f2)
    lw = b2[2] - b2[0]
    d.text((cx - lw / 2 - b2[0], 214 - b2[1]), label, font=f2, fill=(226, 232, 240, 255))

    if size != s:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = render(BASE)
    base.save(OUT, format="ICO", sizes=[(sz, sz) for sz in sizes])
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
