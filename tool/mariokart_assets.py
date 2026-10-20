#!/usr/bin/env python3
"""
Asset pipeline for the Mario Karts game (games/mariokart/).

Turns the 15-sprite contact sheet (a 4x4 grid of 252x252 3D renders on a
baked checkerboard background) into every binary asset the game loads on
its three targets:

  Thumby      : 2-bit BIT/SHD sprite planes (4-level dither), 1-bit
                74x30 loader intro
  ThumbyColor : RGB565 COL sprites (8-byte header, key-transparent)
  shared      : TDL8 128x80 intro cutscene, 96x58 game icon

Sprite set (the karts are rear-view renders - ideal for a behind-the-kart
top-down racer):

  karts0-7    : 20x17 BIT/SHD (both targets' small sprites, scaled at
                runtime), 40x34 COL (the player's kart on the color
                target), 20x17 COL (AI karts on the color target)
  items       : mushroom / star / banana / pokey at 8x8 + 12x12 BIT/SHD
                and 14x14 + 32x32 COL
  obstacles   : cactus / tree / streetlamp at 14x18 / 16x16 / 7x17
                BIT/SHD and 28x36 / 32x32 / 14x34 COL

Nothing here touches the Thumby device; it is a pure host-side build
step (like tool/mariocards_assets.py). Run:

    python3 tool/mariokart_assets.py
    python3 tool/mariokart_assets.py --sheet /path/to/contact_sheet.png
    python3 tool/mariokart_assets.py --preview /tmp/mkprev
"""

import argparse
import importlib.util
import math
import os
import struct

from PIL import Image, ImageChops

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES_DIR = os.path.join(REPO_ROOT, 'games', 'mariokart')
ASSETS_DIR = os.path.join(GAMES_DIR, 'assets')

# --- Contact sheet geometry ---------------------------------------------------
# 14px border, 252px cells, 8px gaps (4x4 grid, 1054x1054 total).
SHEET_CELL = 252
SHEET_GAP = 8
SHEET_ORIGIN = 14
# The background is a baked 16px checkerboard in two colors; the top-left
# 16px square of every cell starts with B.
CHECK_A = (60, 64, 80)
CHECK_B = (80, 84, 100)
CHECK_TOL = 20          # per-channel tolerance for background detection
CHECKER_SIZE = 16

# Sprite order in the grid (row-major). The 16th cell is empty.
GRID_NAMES = [
    'cactus', 'streetlamp', 'tree', 'banana',
    'mushroom', 'pokey', 'star', 'kart0',
    'kart1', 'kart2', 'kart3', 'kart4',
    'kart5', 'kart6', 'kart7', None,
]

# The magic color used for COL transparency: pure magenta, which none of
# the sprites contain. The pipeline asserts no sprite pixel quantizes to
# it, and the game uses the same constant when drawing.
KEY_MAGIC = 0xF81F

KART_NAMES = ['RED', 'BLUE', 'ORANGE', 'GREEN',
              'PINK', 'MINT', 'TEAL', 'YELLOW']

# --- UI / world colors (RGB; the game's constants.py carries the RGB565) ------
C_BG = (40, 44, 60)
C_GRASS = (46, 96, 58)
C_GRASS2 = (52, 110, 66)
C_ROAD = (88, 92, 104)
C_ROAD_EDGE = (235, 238, 245)
C_TEXT = (235, 238, 245)
C_TEXT_DIM = (120, 126, 145)
C_SELECT = (255, 238, 0)


def rgb565(rgb):
    r, g, b = rgb
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


# --- Contact sheet extraction ---------------------------------------------------

def extract_cell(sheet, cell_x, cell_y):
    """Cut one 252x252 cell and mask out the baked checkerboard.

    Returns an RGBA image (trimmed to the sprite bounding box) where the
    checkerboard pixels are fully transparent.
    """
    ox = SHEET_ORIGIN + cell_x * (SHEET_CELL + SHEET_GAP)
    oy = SHEET_ORIGIN + cell_y * (SHEET_CELL + SHEET_GAP)
    cell = sheet.crop((ox, oy, ox + SHEET_CELL, oy + SHEET_CELL))
    px = cell.load()

    # Determine which checker square covers each pixel; a pixel that
    # matches its *expected* background color within tolerance is part
    # of the background (more robust than matching either color: a
    # sprite pixel equal to the *other* square's color stays
    # foreground).
    mask = [[False] * SHEET_CELL for _ in range(SHEET_CELL)]
    for cy in range(SHEET_CELL):
        row_even = (cy // CHECKER_SIZE) % 2
        for cx in range(SHEET_CELL):
            r, g, b, a = px[cx, cy]
            if a < 8:
                mask[cy][cx] = True
                continue
            expected = CHECK_B if ((cx // CHECKER_SIZE) + row_even) % 2 == 0 \
                else CHECK_A
            if (abs(r - expected[0]) <= CHECK_TOL and
                    abs(g - expected[1]) <= CHECK_TOL and
                    abs(b - expected[2]) <= CHECK_TOL):
                mask[cy][cx] = True

    # Trim to the bounding box of foreground pixels.
    xs = [x for x in range(SHEET_CELL)
          if any(not mask[y][x] for y in range(SHEET_CELL))]
    ys = [y for y in range(SHEET_CELL)
          if any(not mask[y][x] for x in range(SHEET_CELL))]
    if not xs or not ys:
        return None
    x0, x1 = xs[0], xs[-1]
    y0, y1 = ys[0], ys[-1]

    out = Image.new('RGBA', (x1 - x0 + 1, y1 - y0 + 1), (0, 0, 0, 0))
    out_px = out.load()
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if not mask[y][x]:
                out_px[x - x0, y - y0] = px[x, y]
    return out


def extract_all(sheet):
    sprites = {}
    for i, name in enumerate(GRID_NAMES):
        if name is None:
            continue
        cell = extract_cell(sheet, i % 4, i // 4)
        if cell is None:
            print(f'  warning: {name} is empty, skipping')
            continue
        sprites[name] = cell
        print(f'  {name:10s} trimmed {cell.size[0]}x{cell.size[1]}')
    return sprites


# --- Scaling helpers ---------------------------------------------------------

def scale_fit(img, w, h):
    """Scale an RGBA image to fit in an wxh box, centered, aspect-kept."""
    iw, ih = img.size
    s = min(w / iw, h / ih)
    nw, nh = max(1, int(iw * s + 0.5)), max(1, int(ih * s + 0.5))
    small = img.resize((nw, nh), Image.LANCZOS)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.paste(small, ((w - nw) // 2, (h - nh) // 2), small)
    return out


def scale_center(img, w, h):
    """Scale keeping aspect, crop/center to exactly wxh (for squares)."""
    iw, ih = img.size
    s = max(w / iw, h / ih)
    nw, nh = max(1, int(iw * s + 0.5)), max(1, int(ih * s + 0.5))
    big = img.resize((nw, nh), Image.LANCZOS)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.paste(big, ((w - nw) // 2, (h - nh) // 2), big)
    return out


# --- COL writer (ThumbyColor / RGB565) -----------------------------------------

def write_col(path, img, w, h, key=KEY_MAGIC, frames=None):
    """Write a .COL.bin: <HHHH> header (w, h, framecount, flags) + RGB565.

    `frames` is a list of RGBA images (all wxh) for multi-frame sprites;
    the default is a single frame from `img`.
    """
    if frames is None:
        frames = [img]
    buf = bytearray(struct.pack('<HHHH', w, h, len(frames), 0))
    for fr in frames:
        if fr.size != (w, h):
            fr = fr.resize((w, h), Image.LANCZOS)
        px = fr.load()
        for y in range(h):
            for x in range(w):
                a = px[x, y][3]
                if a < 8:
                    val = key
                else:
                    r, g, b = px[x, y][:3]
                    val = rgb565((r, g, b))
                # The magic key must never appear as a real sprite color.
                if val == key and a >= 8:
                    raise AssertionError(
                        f'{path}: sprite pixel quantized to the magic '
                        f'key ({val:#06x}); pick a different key')
                buf += struct.pack('<H', val)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(buf)
    return len(buf)


# --- BIT/SHD writer (Thumby / 2-bit dither) ------------------------------------

def _dither_4level(img, w, h, bands=True):
    """Floyd-Steinberg dither of an RGBA image to 4 brightness levels.

    Level 0 = off (background), 1 = dim, 2 = mid, 3 = bright white.
    levels_to_planes() converts this brightness order into the engine's
    plane-index order (0=off, 1=white, 2=dark, 3=mid - see
    thumby_engine/display/grayscale.py _init_grayscale: (BIT,SHD)
    (1,0)=3/3 white, (1,1)=2/3 mid, (0,1)=1/3 dark).

    bands=True uses a dead-zone quantizer: gradient interiors snap to a
    flat level and only the narrow transition zones dither. On 3D-shaded
    sprites (the karts) that reads as clean banded shading instead of
    FS grain; the error diffusion still anti-aliases the band edges.
    Returns a list of (h rows of w int levels).
    """
    if img.size != (w, h):
        img = img.resize((w, h), Image.LANCZOS)
    px = img.load()

    level = [[0.0] * w for _ in range(h)]
    fg = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 20:
                continue
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            level[y][x] = 3.0 * (lum / 255.0)
            fg[y][x] = True

    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if not fg[y][x]:
                continue
            v = level[y][x]
            if bands:
                f = v - int(v)
                if 0.35 <= f <= 0.65:
                    q = int(v + 0.5)          # near a half-integer: round
                elif f < 0.35:
                    q = int(v)                # dead zone: hold the level
                else:
                    q = int(v) + 1
            else:
                q = int(v + 0.5)
            if q < 0:
                q = 0
            elif q > 3:
                q = 3
            out[y][x] = q
            err = v - q
            # Classic FS weights, spread only to foreground neighbors so
            # the transparent background stays clean.
            if x + 1 < w and fg[y][x + 1]:
                level[y][x + 1] += err * (7 / 16)
            if y + 1 < h:
                if x > 0 and fg[y + 1][x - 1]:
                    level[y + 1][x - 1] += err * (3 / 16)
                if fg[y + 1][x]:
                    level[y + 1][x] += err * (5 / 16)
                if x + 1 < w and fg[y + 1][x + 1]:
                    level[y + 1][x + 1] += err * (1 / 16)
    return out


# Brightness order (what _dither_4level and the intro code use) ->
# engine plane-index order: the display mixes (BIT,SHD) as
# (0,0)=off, (0,1)=1/3 dark, (1,1)=2/3 mid, (1,0)=3/3 white.
_B2E = (0, 2, 3, 1)


def levels_to_planes(levels, w, h):
    """Pack 4-level rows into (BIT, SHD) byte planes, SSD1306 layout.

    byte index = (y // 8) * width + x, bit index = y & 7 (bit 0 = top).
    Levels are brightness-ordered; they are remapped to the engine's
    plane-index order first (bit 0 -> BIT file, bit 1 -> SHD file, as
    in tool/grayscale_video_generator.py).
    """
    bit = bytearray((h // 8 + (1 if h % 8 else 0)) * w)
    shd = bytearray(len(bit))
    for y in range(h):
        for x in range(w):
            eng = _B2E[levels[y][x]]
            o = (y >> 3) * w + x
            m = 1 << (y & 7)
            if eng & 1:
                bit[o] |= m
            if eng & 2:
                shd[o] |= m
    return bytes(bit), bytes(shd)


def write_bit_shd(path_bit, path_shd, img, w, h, frames=None):
    """Write a (BIT, SHD) sprite pair from one or more RGBA images."""
    if frames is None:
        frames = [img]
    bit_all = bytearray()
    shd_all = bytearray()
    for fr in frames:
        levels = _dither_4level(fr, w, h)
        bit, shd = levels_to_planes(levels, w, h)
        bit_all += bit
        shd_all += shd
    os.makedirs(os.path.dirname(path_bit), exist_ok=True)
    with open(path_bit, 'wb') as fh:
        fh.write(bit_all)
    with open(path_shd, 'wb') as fh:
        fh.write(shd_all)
    return len(bit_all)


# --- TDL8 encoder ---------------------------------------------------------------
# TDL8 format (decoded by thumby_engine/cutscene/color.py):
#   'TDL8' <HHH> (w, h, framecount)
#   256 x 2-byte RGB565 palette
#   framecount x 4-byte little-endian frame offsets
#   frames, each: 8-byte header, byte0 = type
#     'F' = FULL  : u32 size + RLE records (index, run-1), run max 256
#     'U' = URRAW : u32 size + raw palette indices
#     'D' = DLTA  : u32 size + (u32 pixel_index, u8 new_index) changes
#     'S' = SAME  : no data
#   (bytes 1-7 of every frame header are reserved/zero)

def median_cut_palette(pixels, target=256):
    """Median-cut quantization of (r,g,b) triples -> target triples."""
    unique = sorted(set(pixels))
    if len(unique) <= target:
        return unique + [(0, 0, 0)] * (target - len(unique))

    boxes = [unique]
    while len(boxes) < target:
        # Split the box with the widest spread, at its longest axis.
        def spread(box):
            best = 0
            for a in range(3):
                vals = [p[a] for p in box]
                best = max(best, max(vals) - min(vals))
            return best
        boxes.sort(key=spread, reverse=True)
        box = boxes.pop(0)
        if not box:
            boxes.append([unique[0]])
            continue
        rs = [p[0] for p in box]
        gs = [p[1] for p in box]
        bs = [p[2] for p in box]
        axis = max(0, 1, 2, key=lambda a:
                   max([p[a] for p in box]) - min([p[a] for p in box]))
        box.sort(key=lambda p: p[axis])
        mid = len(box) // 2
        if mid == 0 or mid == len(box):
            continue
        boxes.append(box[:mid])
        boxes.append(box[mid:])

    palette = []
    for box in boxes:
        if not box:
            palette.append((0, 0, 0))
            continue
        n = len(box)
        palette.append(tuple(sum(p[i] for p in box) // n for i in range(3)))
    return palette


def build_bucket_lookup(palette_rgb):
    """(r>>3, g>>2, b>>3) bucket -> palette index (fast nearest color)."""
    lookup = {}
    for bi, (pr, pg, pb) in enumerate(palette_rgb):
        bucket = (pr >> 3, pg >> 2, pb >> 3)
        if bucket not in lookup:
            lookup[bucket] = bi
    for r5 in range(32):
        for g6 in range(64):
            for b5 in range(32):
                bucket = (r5, g6, b5)
                if bucket in lookup:
                    continue
                r, g, b = r5 * 8 + 4, g6 * 4 + 2, b5 * 8 + 4
                best, best_d = 0, None
                for bi, (pr, pg, pb) in enumerate(palette_rgb):
                    d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
                    if best_d is None or d < best_d:
                        best, best_d = bi, d
                lookup[bucket] = best
    return lookup


class TDL8Encoder:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.frames_rgb = []      # raw pixel lists, quantized in encode()
        self.palette_rgb = None
        self.lookup = None

    def add_frame(self, rgb_image):
        img = rgb_image.convert('RGB') if rgb_image.mode != 'RGB' \
            else rgb_image
        if img.size != (self.w, self.h):
            img = img.resize((self.w, self.h), Image.LANCZOS)
        self.frames_rgb.append(list(img.getdata()))

    @staticmethod
    def _frame_header(type_byte, data_size):
        # The decoder reads 8 bytes: byte 0 = type, bytes 4..7 = u32
        # little-endian data size, the rest padding.
        return bytes((type_byte, 0, 0, 0)) + struct.pack('<I', data_size)

    @staticmethod
    def _rle(idx):
        """RLE stream: (index, count-1) records, count 1..256 (the
        decoder adds 1). Long runs are split into 256-pixel records."""
        out = bytearray()
        i = 0
        total = len(idx)
        while i < total:
            v = idx[i]
            j = i
            while j < total and idx[j] == v:
                j += 1
            run = j - i
            while run > 0:
                n = min(run, 256)
                out += bytes((v, n - 1))
                run -= n
            i = j
        return bytes(out)

    def encode(self):
        assert self.frames_rgb, 'no frames added'
        # Palette from a strided sample of the whole animation.
        sample = []
        for i, fr in enumerate(self.frames_rgb):
            step = 8 if i < 8 else 64
            sample.extend(fr[::step])
        self.palette_rgb = median_cut_palette(sample)
        self.lookup = build_bucket_lookup(self.palette_rgb)

        frames = []
        for fr in self.frames_rgb:
            frames.append([self.lookup[(r >> 3, g >> 2, b >> 3)]
                           for (r, g, b) in fr])

        pal = bytearray()
        for (r, g, b) in self.palette_rgb:
            pal += struct.pack('<H', rgb565((r, g, b)))

        # Encode each frame: F (RLE full) for the first, then D (delta)
        # when cheaper than 5 bytes/pixel, F otherwise, S for no change.
        body_frames = []
        prev = None
        for idx in frames:
            if prev is None:
                data = self._rle(idx)
                body_frames.append(b'F' + self._frame_header(0, len(data))[1:] + data)
            else:
                changes = [(x, idx[x]) for x in range(len(idx))
                           if idx[x] != prev[x]]
                if not changes:
                    body_frames.append(b'S' + self._frame_header(0, 0)[1:])
                elif len(changes) * 5 < len(idx):
                    blob = struct.pack('<I', len(changes))
                    for x, v in changes:
                        blob += struct.pack('<IB', x, v)
                    body_frames.append(
                        b'D' + self._frame_header(0, len(blob))[1:] + blob)
                else:
                    data = self._rle(idx)
                    body_frames.append(
                        b'F' + self._frame_header(0, len(data))[1:] + data)
            prev = idx

        out = bytearray(b'TDL8')
        out += struct.pack('<HHH', self.w, self.h, len(body_frames))
        out += pal
        # Offset table: absolute file positions of each 8-byte frame
        # header (base = 4-byte magic + 6-byte dims + palette + table).
        off = 10 + len(pal) + 4 * len(body_frames)
        for fd in body_frames:
            out += struct.pack('<I', off)
            off += len(fd)
        for fd in body_frames:
            out += fd
        return bytes(out)


# --- 8x8 font (from the PC framebuf, loaded directly) ---------------------------

def load_font8x8():
    """Load FONT_DATA straight from thumby_engine/pc/framebuf.py without
    importing the package (it drags in pygame lazily - keep the tool
    lean and dependency-free)."""
    path = os.path.join(REPO_ROOT, 'thumby_engine', 'pc', 'framebuf.py')
    spec = importlib.util.spec_from_file_location('_framebuf', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FONT_DATA


# --- 1-bit 74x30 loader intro ---------------------------------------------------

def font8x8_glyphs():
    """Decode FONT_DATA (thumby_engine/pc/framebuf.py): 96 glyphs for
    0x20..0x7F, 8 column bytes each, bit 0 = top row. This is the same
    built-in font the ThumbyColor firmware and the PC use for text, so
    the intro title matches the in-game look on every target."""
    fd = load_font8x8()
    n = len(fd) // 8
    glyphs = {}
    for i in range(n):
        g = [[0] * 8 for _ in range(8)]
        for col in range(8):
            b = fd[i * 8 + col]
            for row in range(8):
                g[row][col] = (b >> row) & 1
        glyphs[chr(0x20 + i)] = g
    return glyphs


def make_thumby_intro(sprites, out_dir, frames=22):
    """Starfield -> MARIO / KARTS (8x8) -> a kart speeds across, 74x30.

    Mirrors the ThumbCommander 1-bit intro (starry background, title
    text, ending star burst) using this game's own sprites. The title
    is baked in with the real 8x8 FONT_DATA glyphs - the tiny 3x5
    firmware font is too crude to downscale, and it is only used for
    in-game labels at runtime (from /lib, like ThumbCommander).
    """
    import random
    w, h = 74, 30
    glyphs = font8x8_glyphs()
    rng = random.Random(7)

    # A fixed starfield; each star is a 1-2px dithered dot with a
    # weight that decides which sub-level it renders at.
    stars = []
    for _ in range(22):
        x = rng.randrange(0, w - 2)
        y = rng.randrange(0, 20)
        stars.append((x, y, rng.random()))

    def starfield():
        lv = [[0] * w for _ in range(h)]
        for sx, sy, bright in stars:
            lv[sy][sx] = 3 if bright > 0.7 else 1
            if sx + 1 < w:
                lv[sy][sx + 1] = 1 if bright > 0.4 else 2
            if sy + 1 < h:
                lv[sy + 1][sx] = 1 if bright > 0.4 else 2
        return lv

    ADV = 9  # 8 wide + 1 space

    def put_text(lv, text, tx, ty, color=3):
        for i, ch in enumerate(text):
            g = glyphs.get(ch)
            if g is None:
                continue
            for row in range(8):
                for col in range(8):
                    if g[row][col]:
                        lv[ty + row][tx + col + i * ADV] = color

    # The player's kart, dithered to 12x10 for the closing sprint.
    kart_img = scale_center(sprites['kart0'], 12, 10)
    kart12 = _dither_4level(kart_img, 12, 10)
    star_img = scale_center(sprites['star'], 10, 10)
    star10 = _dither_4level(star_img, 10, 10)

    title1, title2 = 'MARIO', 'KARTS'
    x1 = (w - (len(title1) - 1) * ADV - 8) // 2
    x2 = (w - (len(title2) - 1) * ADV - 8) // 2
    y1, y2 = 1, 11
    sx0 = (w - 10) // 2
    sy0 = 20

    frames_lv = []
    # Phase 1 (0-4): starfield appears.
    for f in range(5):
        lv = starfield()
        for sx, sy, bright in stars:
            if bright < f * 0.18:
                lv[sy][sx] = 0
        frames_lv.append(lv)
    # Phase 2 (5-14): title types on.
    for f in range(10):
        lv = starfield()
        reveal = (f + 1) * 11 // 10          # 1..11 chars
        put_text(lv, title1[:min(5, reveal)], x1, y1)
        put_text(lv, title2[:max(0, reveal - 5)], x2, y2)
        frames_lv.append(lv)
    # Phase 3 (15-21): a kart sprints left-to-right across the star
    # field, then a star pops where it stopped.
    for f in range(7):
        lv = starfield()
        put_text(lv, title1, x1, y1)
        put_text(lv, title2, x2, y2)
        if f <= 4:
            kx = -14 + f * 22
            if kx + 12 > 0:
                for yy in range(10):
                    for xx in range(12):
                        v = kart12[yy][xx]
                        if v:
                            x = kx + xx
                            if 0 <= x < w:
                                lv[sy0 + yy][x] = v
        else:
            # Burst: the star lands center-bottom.
            for yy in range(10):
                for xx in range(10):
                    v = star10[yy][xx]
                    if v:
                        lv[sy0 + yy][sx0 + xx] = v
            if f >= 6:
                cx, cy = sx0 + 5, sy0 + 5
                for a in range(0, 360, 45):
                    px_ = cx + int(7 * math.cos(math.radians(a)))
                    py_ = cy + int(7 * math.sin(math.radians(a)))
                    if 0 <= px_ < w and 0 <= py_ < h:
                        lv[py_][px_] = 3
        frames_lv.append(lv)

    bit_all = bytearray()
    shd_all = bytearray()
    for lv in frames_lv[:frames]:
        bit, shd = levels_to_planes(lv, w, h)
        bit_all += bit
        shd_all += shd
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'intro_74_30.BIT.bin'), 'wb') as fh:
        fh.write(bit_all)
    with open(os.path.join(out_dir, 'intro_74_30.SHD.bin'), 'wb') as fh:
        fh.write(shd_all)
    print(f'  intro_74_30: {len(frames_lv[:frames])} frames @ 8 Hz '
          f'({len(bit_all)} bytes/plane)')


def paste_rgba(dst, src, pos):
    """Alpha-respecting paste of an RGBA sprite onto an RGB frame.

    Image.paste(img, pos, img) ignores the source's alpha channel and
    blends its transparent-black corners, so sprites would get dark
    halos; alpha_composite keeps them clean. Partially off-screen
    sprites are cropped to the visible part.
    """
    x, y = pos
    sx0 = max(0, -x)
    sy0 = max(0, -y)
    sx1 = src.width - max(0, x + src.width - dst.width)
    sy1 = src.height - max(0, y + src.height - dst.height)
    if sx0 >= sx1 or sy0 >= sy1:
        return dst
    part = src.crop((sx0, sy0, sx1, sy1))
    layer = dst.convert('RGBA')
    layer.alpha_composite(part, (max(0, x), max(0, y)))
    return layer.convert('RGB')


# --- TDL8 128x80 color intro -----------------------------------------------------

def make_color_intro(sprites, out_dir, width=128, height=80, fps=21):
    """MARIO KARTS intro cutscene: title types on over a gradient, then
    eight karts race across a road strip with items and obstacles,
    ending on a star pop."""
    enc = TDL8Encoder(width, height)
    font8x8 = load_font8x8()

    # Pre-render the building blocks once.
    star_img = scale_center(sprites['star'], 44, 44)
    karts = [scale_fit(sprites[f'kart{i}'], 22, 18) for i in range(8)]
    cactus = scale_fit(sprites['cactus'], 14, 18)
    tree = scale_fit(sprites['tree'], 22, 22)
    lamp = scale_fit(sprites['streetlamp'], 8, 20)
    banana = scale_fit(sprites['banana'], 12, 10)
    mushroom = scale_fit(sprites['mushroom'], 12, 12)
    pokey = scale_fit(sprites['pokey'], 12, 12)

    # Background: vertical gradient + a road strip at the bottom.
    bg = Image.new('RGB', (width, height))
    bg_px = bg.load()
    for y in range(height):
        t = y / (height - 1)
        r = int(30 + 16 * (1 - t))
        g = int(34 + 20 * (1 - t))
        b = int(54 + 26 * (1 - t))
        for x in range(width):
            bg_px[x, y] = (r, g, b)
    # Road: asphalt with a white edge line and a dashed center line.
    ry0, ry1 = height - 34, height
    for y in range(ry0, ry1):
        for x in range(width):
            if y == ry0 or y == ry1 - 1:
                bg_px[x, y] = (235, 238, 245)
            else:
                bg_px[x, y] = (88, 92, 104)
    for y in range(ry0 + 2, ry1 - 2):
        for x in range(0, width, 16):
            for xx in range(8):
                if x + xx < width:
                    bg_px[x + xx, y] = (200, 204, 214)

    def draw_text(img, text, x, y, color):
        dp = img.load()
        cx = x
        for ch in text:
            code = ord(ch)
            if 32 <= code <= 127:
                off = (code - 32) * 8
                for bx in range(8):
                    byte = font8x8[off + bx]
                    for by in range(8):
                        if byte & (1 << by):
                            xx, yy = cx + bx, y + by
                            if 0 <= xx < width and 0 <= yy < height:
                                dp[xx, yy] = color
            cx += 8
        return img

    # Fixed furniture on both sides of the road.
    furn = [(cactus, (6, ry0 - 19)), (tree, (width - 28, ry0 - 23)),
            (lamp, (30, ry0 - 21)), (cactus, (width - 20, ry0 - 19)),
            (lamp, (width - 46, ry0 - 21)), (tree, (52, ry0 - 23))]

    total = 60
    for f in range(total):
        img = bg.copy()
        for sprite_img, pos in furn:
            img = paste_rgba(img, sprite_img, pos)
        # 1. Star: eases in over frames 1-8, then pulses.
        if f >= 1:
            appear = min(1.0, f / 8)
            pulse = 1.0 + 0.08 * math.sin(f / 3.5)
            s = int(44 * appear * pulse)
            if s >= 8:
                star = star_img.resize((s, s), Image.LANCZOS)
                a = star.getchannel('A')
                rad = s / 2
                mask = Image.new('L', (s, s), 255)
                mp = mask.load()
                for yy in range(s):
                    for xx in range(s):
                        d2 = math.hypot(xx - s / 2, yy - s / 2)
                        mp[xx, yy] = int(255 * max(0.0,
                                   1.0 - max(0.0, (d2 - rad * 0.72) /
                                              (rad * 0.28))))
                star.putalpha(ImageChops.multiply(a, mask))
                img = paste_rgba(img, star,
                                 ((width - s) // 2, 2 + (44 - s) // 2))
        # 2. Title: MARIO / KARTS typing on from frame 10.
        if f >= 10:
            reveal = min(11, (f - 9) * 11 // 16)
            t1 = 'MARIO'[:max(0, reveal)]
            t2 = 'KARTS'[:max(0, reveal - 5)]
            if t1:
                img = draw_text(img, t1, (width - len(t1) * 8) // 2,
                                 52, (255, 255, 255))
            if t2:
                img = draw_text(img, t2, (width - len(t2) * 8) // 2,
                                 61, (255, 238, 0))
        # 3. Karts race across the road from frame 26 on, staggered.
        if f >= 26:
            kx0 = -40 + (f - 26) * 3.2
            for k in range(8):
                kx = int(kx0 + (k % 4) * 26 + (k // 4) * 5 +
                         k * (f - 26) * 0.06)
                if kx < width + 4:
                    img = paste_rgba(img, karts[k],
                                     (kx, ry0 + 8 + (k % 2) * 2))
            # A banana and a mushroom rolling the other way.
            bx = int(width + 10 - (f - 26) * 2.0)
            if -12 < bx < width + 2:
                img = paste_rgba(img, banana, (bx, ry0 + 5))
            mx = int(width + 30 - (f - 26) * 1.7)
            if -12 < mx < width + 2:
                img = paste_rgba(img, pokey, (mx, ry0 + 16))
        enc.add_frame(img)

    os.makedirs(out_dir, exist_ok=True)
    blob = enc.encode()
    path = os.path.join(out_dir, f'intro_{width}_{height}.COL.bin')
    with open(path, 'wb') as fh:
        fh.write(blob)
    print(f'  intro_{width}_{height}.COL.bin: {len(blob)} bytes, '
          f'{total} frames @ {fps} fps')


# --- icon.bmp (ThumbyColor game browser) -----------------------------------------

def make_icon(sprites, path):
    """96x58 24-bit BMP: a big center kart on a checker road strip,
    a star above it."""
    w, h = 96, 58
    img = Image.new('RGB', (w, h), (40, 44, 60))
    px = img.load()
    for y in range(h - 18, h):
        for x in range(w):
            px[x, y] = (88, 92, 104)
    # Checker start-line across the top of the road.
    for y in range(h - 18, h - 15):
        for x in range(0, w, 6):
            for xx in range(6):
                if (x // 6 + y) % 2 == 0:
                    px[x + xx, y] = (240, 242, 248)
                else:
                    px[x + xx, y] = (30, 32, 40)
    star = scale_center(sprites['star'], 30, 30)
    a = star.getchannel('A')
    mask = Image.new('L', (30, 30), 255)
    mp = mask.load()
    for yy in range(30):
        for xx in range(30):
            d2 = math.hypot(xx - 15, yy - 15)
            mp[xx, yy] = int(255 * max(0.0, 1.0 - max(0.0, (d2 - 9) / 6)))
    star.putalpha(ImageChops.multiply(a, mask))
    layer = img.convert('RGBA')
    layer.alpha_composite(star, ((w - 30) // 2, 4))
    img = layer.convert('RGB')
    k1 = scale_fit(sprites['kart0'], 34, 28)
    img = paste_rgba(img, k1, ((w - 34) // 2, h - 32))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, 'BMP')
    print(f'  icon.bmp: {w}x{h}')


# --- Preview ----------------------------------------------------------------------

def write_preview_rgba(img, path, scale=4):
    big = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    check = Image.new('RGBA', big.size, (60, 64, 80, 255))
    cp = check.load()
    cs = 8 * scale
    for y in range(big.height):
        for x in range(big.width):
            if ((x // cs) + (y // cs)) % 2 == 0:
                cp[x, y] = (80, 84, 100, 255)
    check.alpha_composite(big)
    check.save(path)


# --- Main --------------------------------------------------------------------------

# Per-sprite target boxes: (name, (bit_w, bit_h), (col_road_w, col_road_h),
# (col_big_w, col_big_h)).
ITEM_SIZES = {
    'mushroom': ((8, 8), (14, 14), (32, 32)),
    'star':     ((8, 8), (14, 14), (32, 32)),
    'banana':   ((8, 8), (14, 14), (32, 32)),
    'pokey':    ((8, 8), (14, 14), (32, 32)),
}
OBSTACLE_SIZES = {
    'cactus':     ((14, 18), (28, 36), None),
    'tree':       ((16, 16), (32, 32), None),
    'streetlamp': ((7, 17), (14, 34), None),
}


def main():
    ap = argparse.ArgumentParser(
        description='Build the Mario Karts asset set.',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sheet',
                    default='/Users/christian/Downloads/contact_sheet.png')
    ap.add_argument('--preview', default=None,
                    help='directory for human-checkable PNG previews')
    args = ap.parse_args()

    print(f'Contact sheet: {args.sheet}')
    sheet = Image.open(args.sheet).convert('RGBA')
    print('Extracting sprites...')
    sprites = extract_all(sheet)

    if args.preview:
        os.makedirs(args.preview, exist_ok=True)
        for name, img in sprites.items():
            write_preview_rgba(img, os.path.join(args.preview,
                                                 f'{name}_raw.png'))
        print(f'  previews -> {args.preview}')

    os.makedirs(ASSETS_DIR, exist_ok=True)

    # --- Karts ----------------------------------------------------------------
    # 20x17 BIT/SHD: both targets use this source (Thumby in-memory,
    # scaled at runtime); the color target also gets a 40x34 for the
    # player's big rear-view kart.
    print('Kart sprites...')
    for i in range(8):
        name = f'kart{i}'
        img = sprites[name]
        write_bit_shd(os.path.join(ASSETS_DIR, f'{name}_20_17.BIT.bin'),
                      os.path.join(ASSETS_DIR, f'{name}_20_17.SHD.bin'),
                      scale_center(img, 20, 17), 20, 17)
        write_col(os.path.join(ASSETS_DIR, f'{name}_40_34.COL.bin'),
                  scale_center(img, 40, 34), 40, 34)
        write_col(os.path.join(ASSETS_DIR, f'{name}_20_17.COL.bin'),
                  scale_fit(img, 20, 17), 20, 17)
        print(f'  {name} ({KART_NAMES[i]}): 20x17 bit+shd, '
              f'40x34 col, 20x17 col')

    # --- Items -----------------------------------------------------------------
    print('Item sprites...')
    for name, (bit_sz, col_road, col_big) in ITEM_SIZES.items():
        img = sprites[name]
        write_bit_shd(os.path.join(ASSETS_DIR,
                                   f'{name}_{bit_sz[0]}_{bit_sz[1]}.BIT.bin'),
                      os.path.join(ASSETS_DIR,
                                   f'{name}_{bit_sz[0]}_{bit_sz[1]}.SHD.bin'),
                      img, *bit_sz)
        write_col(os.path.join(ASSETS_DIR,
                               f'{name}_{col_road[0]}_{col_road[1]}.COL.bin'),
                  scale_fit(img, *col_road), *col_road)
        write_col(os.path.join(ASSETS_DIR,
                               f'{name}_{col_big[0]}_{col_big[1]}.COL.bin'),
                  scale_fit(img, *col_big), *col_big)
        print(f'  {name}: {bit_sz[0]}x{bit_sz[1]} bit+shd, '
              f'{col_road[0]}x{col_road[1]} col, '
              f'{col_big[0]}x{col_big[1]} col')

    # --- Obstacles ---------------------------------------------------------------
    print('Obstacle sprites...')
    for name, (bit_sz, col_big, _) in OBSTACLE_SIZES.items():
        img = sprites[name]
        write_bit_shd(os.path.join(ASSETS_DIR,
                                   f'{name}_{bit_sz[0]}_{bit_sz[1]}.BIT.bin'),
                      os.path.join(ASSETS_DIR,
                                   f'{name}_{bit_sz[0]}_{bit_sz[1]}.SHD.bin'),
                      img, *bit_sz)
        write_col(os.path.join(ASSETS_DIR,
                               f'{name}_{col_big[0]}_{col_big[1]}.COL.bin'),
                  scale_fit(img, *col_big), *col_big)
        print(f'  {name}: {bit_sz[0]}x{bit_sz[1]} bit+shd, '
              f'{col_big[0]}x{col_big[1]} col')

    # --- Intros -----------------------------------------------------------------
    print('Intros...')
    make_thumby_intro(sprites, ASSETS_DIR)
    make_color_intro(sprites, ASSETS_DIR)

    # --- Icon --------------------------------------------------------------------
    print('Icon...')
    make_icon(sprites, os.path.join(GAMES_DIR, 'icon.bmp'))

    total = sum(os.path.getsize(os.path.join(ASSETS_DIR, f))
                for f in os.listdir(ASSETS_DIR))
    print(f'Done. {len(os.listdir(ASSETS_DIR))} asset files, '
          f'{total // 1024} KiB total in {ASSETS_DIR}')


if __name__ == '__main__':
    main()
