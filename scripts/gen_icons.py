#!/usr/bin/env python3
"""Generate the PWA icons for recipe-db — deterministic, stdlib-only.

Draws an industrial monogram: dark slate tile + petrol "R" built from
geometric primitives (bar, bowl, leg). Outputs PNGs into static/icons/.

Run:  python3 scripts/gen_icons.py
"""
import os
import struct
import zlib

ACCENT = (31, 154, 180, 255)      # #1f9ab4
TILE = (31, 44, 56, 255)          # djup skifferblå (rail-familjen)


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def write_png(path: str, size: int, pixels: list) -> None:
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter: none
        for x in range(size):
            raw.extend(pixels[y * size + x])
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + _png_chunk(b"IHDR", ihdr)
           + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + _png_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def _in_r(x: float, y: float) -> bool:
    """Glyph coverage for the 'R' — 0..1 fractional canvas coords.

    Uppbyggd som ett tryckt R: stam + halv-D-skål fäst i stammen
    + ben som går från skålens botten ned till baslinjen.
    """
    # vertikal stam
    if 0.18 <= x <= 0.32 and 0.10 <= y <= 0.88:
        return True
    # skål: högra halvan av en cirkel vars diameter sitter på stammen
    cx, cy, r = 0.32, 0.295, 0.205
    if x >= cx and (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
        return True
    # ben: från stammen strax under skålen ned till höger
    if 0.36 <= x <= 0.72:
        t = (x - 0.36) / 0.36
        y_line = 0.52 + t * 0.34
        if abs(y - y_line) <= 0.055:
            return True
    return False


def render(size: int, glyph_scale: float, maskable: bool) -> list:
    px = []
    for y in range(size):
        for x in range(size):
            bg = TILE if maskable else TILE
            # om maskable: fyll hela canvas med tile
            c = x / (size - 1), y / (size - 1)
            # centrera glyfen med glyph_scale
            gx = (c[0] - 0.5) / glyph_scale + 0.5
            gy = (c[1] - 0.5) / glyph_scale + 0.5
            if 0.0 <= gx <= 1.0 and 0.0 <= gy <= 1.0 and _in_r(gx, gy):
                px.append(ACCENT)
            else:
                px.append(bg)
    return px


def main() -> None:
    out = os.path.join(os.path.dirname(__file__), "..", "static", "icons")
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    targets = [
        ("icon-192.png", 192, 0.78, False),
        ("icon-512.png", 512, 0.78, False),
        ("icon-maskable-512.png", 512, 0.58, True),
        ("apple-touch-icon.png", 180, 0.78, False),
    ]
    for name, size, scale, maskable in targets:
        write_png(os.path.join(out, name), size, render(size, scale, maskable))
        print(f"wrote {name} ({size}x{size})")


if __name__ == "__main__":
    main()