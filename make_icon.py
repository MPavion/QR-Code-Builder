#!/usr/bin/env python3
"""Generate the QR Code Builder app icon (PNG 1024x1024 + multi-res ICO)."""
import os
import random
from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]
CANVAS = 1024
BG     = "#1a1a2e"
FG     = "#4ecca3"   # teal – main modules
ACC    = "#e94560"   # red  – accent corner + scattered dots
CORNER_RADIUS = 80


def _rgba(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _draw_finder(draw, ox, oy, cell, fg, bg):
    """Draw a standard 7×7 QR finder pattern."""
    fc, bc = _rgba(fg), _rgba(bg)
    for row in range(7):
        for col in range(7):
            on_border = row in (0, 6) or col in (0, 6)
            in_centre = 2 <= row <= 4 and 2 <= col <= 4
            fill = fc if (on_border or in_centre) else bc
            x0, y0 = ox + col * cell, oy + row * cell
            draw.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1], fill=fill)


def make_icon(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)

    img  = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded background
    draw.rounded_rectangle([0, 0, CANVAS - 1, CANVAS - 1],
                            radius=CORNER_RADIUS, fill=_rgba(BG))

    PAD  = 50
    grid = CANVAS - 2 * PAD          # usable square
    cell = grid // 21                 # 21 modules = smallest QR version
    grid = cell * 21                  # snap to exact multiple
    ox   = (CANVAS - grid) // 2
    oy   = (CANVAS - grid) // 2

    # Three finder patterns (TL, TR, BL) – BL uses accent colour
    _draw_finder(draw, ox,                   oy,                   cell, FG,  BG)
    _draw_finder(draw, ox + (21 - 7) * cell, oy,                   cell, FG,  BG)
    _draw_finder(draw, ox,                   oy + (21 - 7) * cell, cell, ACC, BG)

    # Timing strips (between finders, rows/cols 6)
    for i in range(8, 13):
        for axis in range(2):
            color = FG if i % 2 == 0 else BG
            fill  = _rgba(color)
            x0 = ox + (i * cell if axis == 0 else 6 * cell)
            y0 = oy + (6 * cell if axis == 0 else i * cell)
            draw.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1], fill=fill)

    # Scattered data modules in the centre region
    rng = random.Random(42)
    for row in range(9, 21):
        for col in range(9, 21):
            if rng.random() > 0.48:
                x0 = ox + col * cell + 2
                y0 = oy + row * cell + 2
                c   = FG if rng.random() > 0.22 else ACC
                fill = _rgba(c, alpha=200)
                draw.rounded_rectangle(
                    [x0, y0, x0 + cell - 4, y0 + cell - 4],
                    radius=max(1, cell // 4),
                    fill=fill,
                )

    # ── Save outputs ─────────────────────────────────────────────────────────
    png_path = os.path.join(out_dir, "icon.png")
    img.save(png_path, format="PNG")
    print(f"  icon.png  {CANVAS}×{CANVAS}px")

    ico_path = os.path.join(out_dir, "icon.ico")
    frames = [img.resize((s, s), Image.LANCZOS).convert("RGBA") for s in SIZES]
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[1:],
    )
    print(f"  icon.ico  ({', '.join(str(s) for s in SIZES)}px)")


if __name__ == "__main__":
    base   = os.path.dirname(os.path.abspath(__file__))
    assets = os.path.join(base, "assets")
    print(f"Generating icons -> {assets}")
    make_icon(assets)
    print("Done.")
