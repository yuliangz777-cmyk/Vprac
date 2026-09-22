#!/usr/bin/env python3
"""Generate the PWA icon set without any imaging dependencies.

Renders the Violin Quest crest (a chevron over four strings) with 3x
supersampling, then box-downsamples to every size the manifest needs.

Usage:  python3 tools/make_icons.py
"""

import os
import struct
import zlib

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")

TOP = (0x45, 0x9E, 0x5E)      # leaf green
BOTTOM = (0x1E, 0x57, 0x31)   # forest green
GOLD = (0xE0, 0xB2, 0x5C)
WHITE = (0xFF, 0xFF, 0xFF)

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


def chevron(scale, cy):
    """Chevron polygon in normalised coords, `scale` shrinks it about (0.5, cy)."""
    pts = [
        (0.215, 0.300), (0.500, 0.790), (0.785, 0.300),
        (0.655, 0.300), (0.500, 0.570), (0.345, 0.300),
    ]
    return [(0.5 + (x - 0.5) * scale, cy + (y - 0.5) * scale) for x, y in pts]


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def blend(base, top, alpha):
    return tuple(int(round(b + (t - b) * alpha)) for b, t in zip(base, top))


def render(size, scale=1.0):
    """Render one square icon; `scale` < 1 keeps the mark inside a maskable safe zone."""
    poly = chevron(0.86 * scale, 0.5)
    dot_c = (0.5, 0.5 + (0.245 - 0.5) * 0.86 * scale)
    dot_r = 0.052 * scale
    string_w = 0.012 * scale
    string_xs = [0.5 + (x - 0.5) * scale for x in (0.335, 0.445, 0.555, 0.665)]
    string_top = 0.5 + (0.13 - 0.5) * scale
    string_bottom = 0.5 + (0.87 - 0.5) * scale

    pixels = bytearray(size * size * 4)
    inv = 1.0 / (size * SS)
    weight = 1.0 / (SS * SS)

    for py in range(size):
        row = py * size * 4
        for px in range(size):
            acc = [0.0, 0.0, 0.0]
            for sy in range(SS):
                v = (py * SS + sy + 0.5) * inv
                # vertical gradient with a soft highlight near the top left
                base = tuple(int(round(t + (b - t) * v)) for t, b in zip(TOP, BOTTOM))
                for sx in range(SS):
                    u = (px * SS + sx + 0.5) * inv
                    color = base
                    glow = max(0.0, 1.0 - (((u - 0.32) ** 2 + (v - 0.24) ** 2) ** 0.5) * 2.1)
                    if glow > 0:
                        color = blend(color, WHITE, glow * 0.16)
                    if string_top <= v <= string_bottom:
                        for sxp in string_xs:
                            if abs(u - sxp) <= string_w * 0.5:
                                color = blend(color, WHITE, 0.16)
                                break
                    if point_in_poly(u, v, poly):
                        color = WHITE
                    if ((u - dot_c[0]) ** 2 + (v - dot_c[1]) ** 2) ** 0.5 <= dot_r:
                        color = GOLD
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
    """Box filter from `size` to `target` (target must divide evenly enough)."""
    out = bytearray(target * target * 4)
    ratio = size / target
    for y in range(target):
        y0 = int(y * ratio)
        y1 = max(y0 + 1, int((y + 1) * ratio))
        for x in range(target):
            x0 = int(x * ratio)
            x1 = max(x0 + 1, int((x + 1) * ratio))
            r = g = b = 0
            count = 0
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
    maskable = render(512, scale=0.72)
    write_png(os.path.join(OUT_DIR, "maskable-512.png"), 512, 512, maskable)

    for name in sorted(os.listdir(OUT_DIR)):
        path = os.path.join(OUT_DIR, name)
        print(f"  {name}: {os.path.getsize(path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
