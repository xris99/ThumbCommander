#!/usr/bin/env python3
"""
mariokart_textures.py - ground/sky texture builder for the MarioKarts
ThumbyColor target (and the PC emulation).

The textures are single-frame RGB565 .COL.bin files (same 8-byte
<HHHH> header as the sprites) that the game loads straight into RAM
and samples per pixel while painting the ground and the sky. The
Thumby (1-bit) target never loads them; the deploy tool filters .COL
files out of the Thumby asset subset.

Sources:
  * sky  - games/mariokart/assets/skybox_src.jpg, a 360x120 sky
    panorama reused from SevEngine v1.2 (MIT License, (c) 2026
    UNTITLED PARSNIP, https://codeberg.org/untitledparsnip/SevEngine).
    Attribution preserved here and in the vendored source.
  * road / grass - procedurally generated tileable tiles in the game's
    world palette (asphalt 0x6B8F, grass 0x6629). All features are
    periodic with the 64 px tile, so the tiles wrap seamlessly in both
    directions.

Usage:
    python3 tool/mariokart_textures.py
"""

import os
import struct

from PIL import Image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO_ROOT, 'games', 'mariokart', 'assets')

SKY_SRC = os.path.join(ASSETS, 'skybox_src.jpg')
SKY_OUT = os.path.join(ASSETS, 'sky_256_34.COL.bin')
ROAD_OUT = os.path.join(ASSETS, 'road_64_64.COL.bin')
GRASS_OUT = os.path.join(ASSETS, 'grass_64_64.COL.bin')

# Horizon row of the ThumbyColor layout; the sky strip covers rows
# 0..HORIZON-1 exactly, so it is scaled to this height.
SKY_W = 256          # power of two: the sky u wraps with a mask
SKY_H = 34
TILE = 64            # ground tile edge, power of two

# World palette targets (RGB888 decoded from constants.py)
ROAD_BASE = (108, 114, 124)   # asphalt (0x6B8F)
GRASS_BASE = (100, 190, 70)   # grass (0x6629 / 0x55C7 midpoint)


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def clamp8(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))


def hash2(x, y, salt=0):
    """Deterministic per-pixel hash, periodic with the 64 px tile."""
    h = (x + 1) * 374761393 + (y + 1) * 668265263 + salt * 1274126177
    h &= 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h & 0xFFFF


def write_col(path, w, h, vals):
    """Write a single-frame RGB565 .COL.bin (8-byte <HHHH> header)."""
    assert len(vals) == w * h
    buf = bytearray(struct.pack('<HHHH', w, h, 1, 0))
    for v in vals:
        buf += struct.pack('<H', v)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(buf)
    print(f'wrote {os.path.basename(path)}: {w}x{h} ({len(buf)} bytes)')


# --- Sky: reuse the SevEngine panorama -------------------------------------

def build_sky():
    img = Image.open(SKY_SRC).convert('RGB')
    # Drop the dark foreground strip at the bottom; the mountain bases
    # become the horizon, which is where the ground texture starts.
    img = img.crop((0, 0, img.size[0], 100))
    img = img.resize((SKY_W, SKY_H), Image.LANCZOS)
    px = img.load()
    vals = [rgb565(*px[x, y][:3]) for y in range(SKY_H)
            for x in range(SKY_W)]
    write_col(SKY_OUT, SKY_W, SKY_H, vals)


# --- Procedural tiles --------------------------------------------------------

def build_road():
    """Tileable asphalt: base gray with fine grain, tire-wear bands at
    fixed cross-road columns and scattered darker patches."""
    vals = []
    for y in range(TILE):
        for x in range(TILE):
            n = hash2(x, y)
            grain = ((n & 255) - 128) * 14 // 255          # +/- 14
            # Tire-wear skid marks at two fixed tire tracks + brighter
            # center seam; constant u so they read as continuous lines.
            wear = 0
            if (x % 64) in range(14, 22) or (x % 64) in range(42, 50):
                wear = -6
            elif (x % 64) in range(30, 36):
                wear = 4
            # Occasional darker oil patch (periodic, wraps at 64).
            patch = 0
            if hash2(x, y, 1) & 0xFF < 10:
                patch = -18
            r, g, b = ROAD_BASE
            r = clamp8(r + grain + wear + patch)
            g = clamp8(g + grain + wear + patch)
            b = clamp8(b + grain + wear + patch)
            vals.append(rgb565(r, g, b))
    write_col(ROAD_OUT, TILE, TILE, vals)


def build_grass():
    """Tileable grass: green base with blade speckles, soft large-scale
    tone variation (periodic) and a few dry flecks."""
    vals = []
    for y in range(TILE):
        for x in range(TILE):
            n = hash2(x, y)
            speck = ((n & 255) - 128) * 18 // 255          # +/- 18
            # Large-scale tone drift, periodic over the tile.
            drift = 10 * ((x % 64) + (y % 64)) // 64 - 10
            r, g, b = GRASS_BASE
            r = clamp8(r + speck // 2 + drift)
            g = clamp8(g + speck + drift)
            b = clamp8(b + speck // 3)
            # Dry flecks: pale yellow patches.
            if hash2(x, y, 7) & 0x1FF < 14:
                r = clamp8(r + 26)
                g = clamp8(g + 10)
                b = clamp8(b - 14)
            vals.append(rgb565(r, g, b))
    write_col(GRASS_OUT, TILE, TILE, vals)


def preview():
    """Write PNG previews of the generated tiles for quick review."""
    for path, name in ((SKY_OUT, 'sky'), (ROAD_OUT, 'road'),
                       (GRASS_OUT, 'grass')):
        with open(path, 'rb') as f:
            w, h = struct.unpack('<HH', f.read(4))
            raw = bytearray(f.read())
        img = Image.new('RGB', (w, h))
        px = img.load()
        for y in range(h):
            for x in range(w):
                v = raw[(y * w + x) * 2] | (raw[(y * w + x) * 2 + 1] << 8)
                r = ((v >> 11) & 31) * 8 + 4
                g = ((v >> 5) & 63) * 4 + 2
                b = (v & 31) * 8 + 4
                px[x, y] = (r, g, b)
        out = f'/tmp/mk_{name}_preview.png'
        img.save(out)
        print(f'preview {out}')


if __name__ == '__main__':
    build_sky()
    build_road()
    build_grass()
    preview()
