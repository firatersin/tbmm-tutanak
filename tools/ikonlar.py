#!/usr/bin/env python3
"""Uygulama ikonlarını static/ altına üretir (tek seferlik; çıktılar repoya eklenir).

  pip install pillow
  python tools/ikonlar.py

Windows'taki Georgia Bold yazı tipini kullanır; başka sistemde FONT yolunu değiştirin.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static"
FONT = "C:/Windows/Fonts/georgiab.ttf"
BG = (30, 82, 96)        # --vurgu (petrol)
FG = (247, 242, 232)    # --kagit
SS = 4                   # kenar yumuşatma için büyük çizip küçült


def draw(size: int, rounded: bool, glyph_scale: float) -> Image.Image:
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * 0.22), fill=BG)
    else:
        d.rectangle([0, 0, big, big], fill=BG)

    font = ImageFont.truetype(FONT, int(big * 0.56 * glyph_scale))
    l, t, r, b = d.textbbox((0, 0), "M", font=font)
    w, h = r - l, b - t
    line_h = max(SS, int(big * 0.035 * glyph_scale))
    gap = int(big * 0.06 * glyph_scale)
    total_h = h + gap + line_h
    x = (big - w) / 2 - l
    y = (big - total_h) / 2 - t
    d.text((x, y), "M", font=font, fill=FG)
    # "M"nin altında kürsüyü andıran ince çizgi
    lw = w * 1.05
    ly = (big - total_h) / 2 + h + gap
    d.rounded_rectangle([(big - lw) / 2, ly, (big + lw) / 2, ly + line_h], radius=line_h // 2, fill=FG)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    draw(192, True, 1.0).save(OUT / "icon-192.png")
    draw(512, True, 1.0).save(OUT / "icon-512.png")
    # Maskeli ikon: Android kendi şeklini uygular; içerik ortadaki güvenli alanda kalmalı
    draw(512, False, 0.72).save(OUT / "icon-maskable-512.png")
    # iOS köşeleri kendisi yuvarlar ve saydamlığı sevmez
    draw(180, False, 0.9).convert("RGB").save(OUT / "apple-touch-icon.png")
    draw(32, True, 1.1).save(OUT / "favicon-32.png")
    print("\n".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
