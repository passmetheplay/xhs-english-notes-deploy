#!/usr/bin/env python3
"""Normalize the later carousel images to the established monochrome style.

The source images already contain approved Chinese and English copy. This
script deliberately does not regenerate or OCR any text; it only removes the
grid-paper/color treatment and maps the artwork to the earlier red/blue/black
palette so the copy stays byte-for-byte represented in the image layout.
"""

from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

from PIL import Image


RED = (218, 47, 39)
BLUE = (35, 91, 190)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def normalize_image(source: Path, target: Path) -> None:
    image = Image.open(source).convert("RGB")
    source_pixels = image.load()
    output = Image.new("RGB", image.size, WHITE)
    output_pixels = output.load()

    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = source_pixels[x, y]
            maximum = max(red, green, blue)
            minimum = min(red, green, blue)
            luminance = 0.299 * red + 0.587 * green + 0.114 * blue
            saturation = (maximum - minimum) / maximum if maximum else 0

            # The new pages use a very light beige grid. Treat those pixels as
            # paper so the background matches the earlier white pages.
            if luminance > 205 and saturation < 0.16:
                output_pixels[x, y] = WHITE
                continue

            hue = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)[0] * 360

            # Preserve the established accent colors, but discard skin, hair,
            # food, and plant colors instead of introducing a new palette.
            if saturation > 0.42 and (hue < 18 or hue > 342) and red - green > 45:
                output_pixels[x, y] = RED
                continue
            if saturation > 0.35 and 195 < hue < 255 and blue - red > 35:
                output_pixels[x, y] = BLUE
                continue

            # Everything else becomes ink or paper, creating the earlier
            # black-line illustration treatment while preserving silhouettes.
            output_pixels[x, y] = BLACK if luminance < 170 else WHITE

    target.parent.mkdir(parents=True, exist_ok=True)
    output.save(target, format="PNG")


def note_number(note_dir: Path) -> int:
    return int(note_dir.name.split("-", 1)[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--start", type=int, default=11)
    args = parser.parse_args()

    notes_root = args.root / "notes"
    note_dirs = sorted(
        path for path in notes_root.iterdir() if path.is_dir() and note_number(path) >= args.start
    )
    if not note_dirs:
        raise SystemExit(f"No note directories found at or after {args.start}")

    processed = 0
    for note_dir in note_dirs:
        for source in sorted((note_dir / "original").glob("*.png")):
            normalize_image(source, source)
            webp = note_dir / "web" / f"{source.stem}.webp"
            Image.open(source).save(webp, format="WEBP", quality=82, method=6)
            processed += 1

    print(f"normalized {processed} images across {len(note_dirs)} notes")


if __name__ == "__main__":
    main()
