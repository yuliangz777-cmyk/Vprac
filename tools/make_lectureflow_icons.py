#!/usr/bin/env python3
"""Generate the LectureFlow PWA icon set without any imaging dependencies.

Renders a microphone under a listening arc with 3x supersampling, then
box-downsamples to every size the manifest needs. Same approach as
tools/make_icons.py, different mark.

Usage:  python3 tools/make_lectureflow_icons.py
"""

import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "lectureflow", "static", "icons")

TOP = (0x2B, 0x2B, 0x2B)      # near-black, slightly lifted
BOTTOM = (0x0E, 0x0E, 0x0E)
WHITE = (0xFF, 0xFF, 0xFF)
GREEN = (0x4E, 0xC9, 0x94)    # the live indicator, same hue as the level meter

SS = 3  # supersampling factor


def write_png(path, width, height, pixels):
    """pixels: bytearray of RGBA rows, length width*height*4."""
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type 0
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def blend(base, top, alpha):
    return tuple(int(round(b + (t - b) * alpha)) for b, t in zip(base, top))


def rounded_rect(u, v, cx, cy, half_w, half_h, radius):
    """True inside an axis-aligned rounded rectangle."""
    dx = abs(u - cx) - (half_w - radius)
    dy = abs(v - cy) - (half_h - radius)
    if dx <= 0 and dy <= 0:
        return True
    dx = max(dx, 0.0)
    dy = max(dy, 0.0)
    return math.hypot(dx, dy) <= radius


def render(size, scale=1.0):
    """Render one square icon; `scale` < 1 keeps the mark in a maskable safe zone."""
    def s(value, centre=0.5):
        return centre + (value - centre) * scale

    cap_cx, cap_cy = 0.5, s(0.395)
    cap_hw, cap_hh = 0.088 * scale, 0.175 * scale
    cap_r = 0.088 * scale

    arc_cx, arc_cy = 0.5, s(0.415)
    arc_outer, arc_inner = 0.268 * scale, 0.230 * scale

    stem_cx, stem_cy = 0.5, s(0.700)
    stem_hw, stem_hh = 0.019 * scale, 0.058 * scale

    base_cx, base_cy = 0.5, s(0.775)
    base_hw, base_hh = 0.105 * scale, 0.020 * scale

    dot_cx, dot_cy = s(0.735), s(0.250)
    dot_r = 0.058 * scale

    pixels = bytearray(size * size * 4)
    inv = 1.0 / (size * SS)
    weight = 1.0 / (SS * SS)

    for py in range(size):
        row = py * size * 4
        for px in range(size):
            acc = [0.0, 0.0, 0.0]
            for sy in range(SS):
                v = (py * SS + sy + 0.5) * inv
                base = tuple(int(round(t + (b - t) * v)) for t, b in zip(TOP, BOTTOM))
                for sx in range(SS):
                    u = (px * SS + sx + 0.5) * inv
                    color = base

                    # soft highlight so the tile does not read as flat black
                    glow = max(0.0, 1.0 - math.hypot(u - 0.30, v - 0.22) * 2.0)
                    if glow > 0:
                        color = blend(color, WHITE, glow * 0.10)

                    # listening arc: lower half of an annulus around the capsule
                    if v >= arc_cy:
                        d = math.hypot(u - arc_cx, v - arc_cy)
                        if arc_inner <= d <= arc_outer:
                            color = WHITE

                    if rounded_rect(u, v, stem_cx, stem_cy, stem_hw, stem_hh, stem_hw):
                        color = WHITE
                    if rounded_rect(u, v, base_cx, base_cy, base_hw, base_hh, base_hh):
                        color = WHITE
                    if rounded_rect(u, v, cap_cx, cap_cy, cap_hw, cap_hh, cap_r):
                        color = WHITE
                    if math.hypot(u - dot_cx, v - dot_cy) <= dot_r:
                        color = GREEN

                    acc[0] += color[0]
                    acc[1] += color[1]
                    acc[2] += color[2]
            i = row + px * 4
            pixels[i] = int(round(acc[0] * weight))
            pixels[i + 1] = int(round(acc[1] * weight))
            pixels[i + 2] = int(round(acc[2] * weight))
            pixels[i + 3] = 255
    return pixels


def downsample(pixels, size, target):
    """Box filter from `size` to `target`."""
    out = bytearray(target * target * 4)
    ratio = size / target
    for y in range(target):
        y0 = int(y * ratio)
        y1 = max(y0 + 1, int((y + 1) * ratio))
        for x in range(target):
            x0 = int(x * ratio)
            x1 = max(x0 + 1, int((x + 1) * ratio))
            r = g = b = count = 0
            for yy in range(y0, y1):
                base = yy * size * 4
                for xx in range(x0, x1):
                    i = base + xx * 4
                    r += pixels[i]
                    g += pixels[i + 1]
                    b += pixels[i + 2]
                    count += 1
            i = (y * target + x) * 4
            out[i] = r // count
            out[i + 1] = g // count
            out[i + 2] = b // count
            out[i + 3] = 255
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("rendering 512x512 master…")
    master = render(512)
    write_png(os.path.join(OUT_DIR, "icon-512.png"), 512, 512, master)

    for name, size in [("icon-256.png", 256), ("icon-192.png", 192),
                       ("apple-touch-icon.png", 180), ("favicon.png", 64)]:
        print(f"downsampling {name}…")
        write_png(os.path.join(OUT_DIR, name), size, size, downsample(master, 512, size))

    print("rendering maskable…")
    write_png(os.path.join(OUT_DIR, "maskable-512.png"), 512, 512, render(512, scale=0.72))

    for name in sorted(os.listdir(OUT_DIR)):
        path = os.path.join(OUT_DIR, name)
        print(f"  {name}: {os.path.getsize(path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
