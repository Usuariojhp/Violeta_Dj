#!/usr/bin/env python3
"""
pwa_assets.py - Genera los iconos PNG de la PWA (vinilo) sin dependencias.
Escribe icon-192.png y icon-512.png en <base_dir>/pwa_icons.
"""
import math
import os
import struct
import zlib


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _png(size, render):
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw.extend(render(x, y, size))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def _clamp(v):
    return max(0, min(255, int(v)))


def _vinyl_render(x, y, size):
    c = size / 2.0
    dx = x - c
    dy = y - c
    d = math.hypot(dx, dy)
    R = size * 0.44
    if d > R:
        return (0, 0, 0, 0)

    t = d / R
    r = 20 + (42 - 20) * t
    g = 26 + (46 - 26) * t
    b = 36 + (56 - 36) * t

    if 0.15 <= t <= 0.95 and int(t * 12) % 2 == 0:
        r += 8
        g += 8
        b += 8

    sx = size * 0.31
    sy = size * 0.27
    sheen = math.exp(-(((x - sx) ** 2 + (y - sy) ** 2)) / (2 * (size * 0.45) ** 2))
    r = r * (1 - sheen * 0.6) + 255 * sheen * 0.6
    g = g * (1 - sheen * 0.6) + 255 * sheen * 0.6
    b = b * (1 - sheen * 0.6) + 255 * sheen * 0.6

    L = size * 0.17
    if d <= L:
        t2 = d / L
        r = 232 + (124 - 232) * t2
        g = 68 + (58 - 68) * t2
        b = 180 + (240 - 180) * t2
        if L * 0.90 <= d <= L * 0.98:
            return (0, 229, 170, 255)

    if d <= size * 0.035:
        return (255, 255, 255, 255)

    return (_clamp(r), _clamp(g), _clamp(b), 255)


def ensure_pwa_assets(base_dir):
    folder = os.path.join(base_dir, "pwa_icons")
    os.makedirs(folder, exist_ok=True)
    paths = {}
    for size in (192, 512):
        path = os.path.join(folder, "icon-{}.png".format(size))
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(_png(size, _vinyl_render))
        paths[size] = path
    return paths


if __name__ == "__main__":
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    out = ensure_pwa_assets(base)
    for k, v in sorted(out.items()):
        print("{} -> {} ({} bytes)".format(k, v, os.path.getsize(v)))