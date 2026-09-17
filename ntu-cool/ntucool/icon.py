"""產生 PWA 需要的 icon，不依賴任何影像套件。

畫法：3 倍超取樣畫一個圓角方塊 + 代表「清單」的三條白槓，再降取樣，邊緣才不會鋸齒。
"""

from __future__ import annotations

import struct
import threading
import zlib

TOP = (0x2B, 0x7C, 0xEA)      # 漸層上緣
BOTTOM = (0x0A, 0x46, 0xA8)   # 漸層下緣
WHITE = (0xFF, 0xFF, 0xFF)
DOT = (0x7F, 0xD4, 0xA0)      # 已完成的那一條前面的點

def _supersample(size: int) -> int:
    """超取樣倍率。大圖用 2 就夠；用 3 會多畫一百多萬個像素，慢到有感。"""
    return 3 if size <= 256 else 2
_CACHE: dict[tuple[int, bool], bytes] = {}


def _png(width: int, height: int, pixels: bytearray) -> bytes:
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type 0
        raw += pixels[y * stride : (y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _rounded_rect(x, y, w, h, radius) -> callable:
    """回傳一個「這個點在不在圓角矩形裡」的函式。"""

    def inside(px, py):
        if not (x <= px < x + w and y <= py < y + h):
            return False
        dx = min(px - x, x + w - 1 - px)
        dy = min(py - y, y + h - 1 - py)
        if dx >= radius or dy >= radius:
            return True
        return (dx - radius) ** 2 + (dy - radius) ** 2 <= radius**2

    return inside


def _render(size: int, square: bool = False) -> bytearray:
    pixels = bytearray(size * size * 4)
    # maskable 與 apple-touch-icon 要滿版：作業系統會自己去切圓角
    card = (lambda *_: True) if square else _rounded_rect(0, 0, size, size, size * 0.22)

    # 三條「清單」白槓，長度不一，最上面那條前面有一個點
    unit = size / 16
    bars = [
        (unit * 5.2, unit * 4.2, unit * 7.2),
        (unit * 3.6, unit * 7.4, unit * 8.8),
        (unit * 3.6, unit * 10.6, unit * 6.4),
    ]
    bar_h = unit * 1.5
    bar_shapes = [(_rounded_rect(x, y, w, bar_h, bar_h / 2)) for x, y, w in bars]
    dot = _rounded_rect(unit * 3.2, unit * 4.2, unit * 1.5, bar_h, bar_h / 2)

    for py in range(size):
        ratio = py / max(1, size - 1)
        bg = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * ratio) for i in range(3))
        for px in range(size):
            offset = (py * size + px) * 4
            if not card(px, py):
                continue  # 圓角外保持透明
            if dot(px, py):
                colour = DOT
            elif any(shape(px, py) for shape in bar_shapes):
                colour = WHITE
            else:
                colour = bg
            pixels[offset : offset + 4] = bytes((*colour, 255))
    return pixels


def _downsample(pixels: bytearray, size: int, target: int) -> bytearray:
    factor = size // target
    out = bytearray(target * target * 4)
    for y in range(target):
        for x in range(target):
            totals = [0, 0, 0, 0]
            for dy in range(factor):
                row = (y * factor + dy) * size
                for dx in range(factor):
                    offset = (row + x * factor + dx) * 4
                    for channel in range(4):
                        totals[channel] += pixels[offset + channel]
            count = factor * factor
            out[(y * target + x) * 4 : (y * target + x) * 4 + 4] = bytes(t // count for t in totals)
    return out


def icon_png(size: int = 192, *, square: bool = False) -> bytes:
    """回傳指定尺寸的 icon PNG（結果會快取，同一種只畫一次）。"""
    key = (size, square)
    if key not in _CACHE:
        factor = _supersample(size)
        big = _render(size * factor, square)
        _CACHE[key] = _png(size, size, _downsample(big, size * factor, size))
    return _CACHE[key]


_PREWARM_LOCK = threading.Lock()
_PREWARMED = False


def prewarm(sizes=((192, False), (512, False), (512, True), (180, True))) -> None:
    """先畫好放著，不要讓使用者的第一個請求等著畫圖。

    整個行程只做一次：多台伺服器（例如測試）不該各自重畫一輪搶 CPU。
    """
    global _PREWARMED
    with _PREWARM_LOCK:
        if _PREWARMED:
            return
        _PREWARMED = True
    for size, square in sizes:
        icon_png(size, square=square)
