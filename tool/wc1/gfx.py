"""Image helpers for the WC1 asset converter (host side, numpy + Pillow).

Everything the device draws comes out of here in one of two forms:

  * sprite sets (.wcs) - 8-bit indexed frames in the game palette, index 0
    = transparent, drawn rotated/scaled by the flight renderer;
  * full pictures (.COL.bin) - the engine's own RGB565 sprite format,
    streamed row by row for cockpits-free screens such as the title.

The original art is 320x200 with 1:1.2 pixels (a 4:3 screen). The
ThumbyColor has square pixels, so every image is resampled into a
square-pixel space: the full screen becomes 128x96.
"""

import struct

import numpy as np

from .shape import TRANSPARENT

# 320x200 (4:3) -> 128x96
SCREEN_SX = 128 / 320
SCREEN_SY = 96 / 200

SPRITE_MAGIC = b'WCS1'


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class Palette:
    def __init__(self, triplets):
        self.rgb = np.array(triplets, dtype=np.float32)        # 256 x 3
        # Index 0 is black in GAME.PAL and doubles as "transparent" in
        # every .wcs file, so opaque black is mapped to the nearest
        # other entry.
        d = ((self.rgb[1:] - self.rgb[0]) ** 2).sum(axis=1)
        self.black = int(np.argmin(d)) + 1
        self._cache = {}

    def as_rgb565_bytes(self):
        out = bytearray()
        for r, g, b in self.rgb.astype(int):
            out += struct.pack('<H', rgb565(int(r), int(g), int(b)))
        return bytes(out)

    def nearest(self, rgb):
        """rgb: (..., 3) float array -> uint8 indices (never 0)."""
        flat = rgb.reshape(-1, 3)
        out = np.empty(len(flat), dtype=np.uint8)
        keys = (flat.astype(np.int32) >> 2)
        packed = (keys[:, 0] << 12) | (keys[:, 1] << 6) | keys[:, 2]
        uniq, inverse = np.unique(packed, return_inverse=True)
        table = np.empty(len(uniq), dtype=np.uint8)
        cand = self.rgb[1:]
        weights = np.array([2.0, 4.0, 3.0], dtype=np.float32)
        for i, key in enumerate(uniq):
            hit = self._cache.get(int(key))
            if hit is None:
                c = np.array([(key >> 12) & 63, (key >> 6) & 63, key & 63],
                             dtype=np.float32) * 4 + 2
                d = (((cand - c) ** 2) * weights).sum(axis=1)
                hit = int(np.argmin(d)) + 1
                self._cache[int(key)] = hit
            table[i] = hit
        out[:] = table[inverse]
        return out.reshape(rgb.shape[:-1])


def frame_to_rgba(frame, palette):
    """shape.Frame -> float32 RGBA array (h, w, 4), alpha 0/1."""
    idx = np.array(frame.pixels, dtype=np.int16)
    alpha = (idx != TRANSPARENT).astype(np.float32)
    rgb = palette.rgb[np.clip(idx, 0, 255)]
    return np.dstack([rgb * alpha[..., None], alpha])


def resample(rgba, out_w, out_h):
    """Area-average premultiplied RGBA to out_w x out_h."""
    h, w = rgba.shape[:2]
    out_w = max(1, int(out_w))
    out_h = max(1, int(out_h))

    def weights(n_in, n_out):
        m = np.zeros((n_out, n_in), dtype=np.float32)
        scale = n_in / n_out
        for o in range(n_out):
            a = o * scale
            b = (o + 1) * scale
            i0 = int(np.floor(a))
            i1 = min(n_in, int(np.ceil(b)))
            for i in range(i0, i1):
                m[o, i] = min(b, i + 1) - max(a, i)
            s = m[o].sum()
            if s > 0:
                m[o] /= s
        return m

    wy = weights(h, out_h)
    wx = weights(w, out_w)
    tmp = np.tensordot(wy, rgba, axes=(1, 0))            # (out_h, w, 4)
    return np.tensordot(tmp, wx, axes=(1, 1)).transpose(0, 2, 1)


def quantize(rgba, palette, threshold=0.42):
    """Premultiplied RGBA -> uint8 indexed image, 0 = transparent."""
    alpha = rgba[..., 3]
    opaque = alpha >= threshold
    safe = np.where(alpha > 1e-6, alpha, 1.0)
    rgb = rgba[..., :3] / safe[..., None]
    idx = palette.nearest(np.clip(rgb, 0, 255))
    return np.where(opaque, idx, 0).astype(np.uint8)


def scale_frame(frame, palette, sx, sy):
    """Resample one shape frame; returns (indexed, hot_x, hot_y) or None.

    The frame is padded so its hot spot lands on a whole output pixel -
    sprites are positioned and rotated around it.
    """
    if frame is None:
        return None
    rgba = frame_to_rgba(frame, palette)
    # pad left/top so the hot spot maps onto an output pixel boundary
    hot_x = int(np.ceil(frame.left * sx))
    hot_y = int(np.ceil(frame.top * sy))
    pad_l = int(round(hot_x / sx)) - frame.left
    pad_t = int(round(hot_y / sy)) - frame.top
    pad_l = max(0, pad_l)
    pad_t = max(0, pad_t)
    out_w = int(np.ceil((frame.width + pad_l) * sx))
    out_h = int(np.ceil((frame.height + pad_t) * sy))
    pad_r = int(round(out_w / sx)) - frame.width - pad_l
    pad_b = int(round(out_h / sy)) - frame.height - pad_t
    rgba = np.pad(rgba, ((pad_t, max(0, pad_b)), (pad_l, max(0, pad_r)),
                         (0, 0)))
    out = quantize(resample(rgba, out_w, out_h), palette)
    # trim fully transparent borders (keeps the hot spot consistent)
    rows = np.flatnonzero(out.any(axis=1))
    cols = np.flatnonzero(out.any(axis=0))
    if len(rows) == 0:
        return None
    y0, y1 = rows[0], rows[-1] + 1
    x0, x1 = cols[0], cols[-1] + 1
    out = out[y0:y1, x0:x1]
    return out, hot_x - x0, hot_y - y0


def write_sprite_set(path, frames, res):
    """frames: list of (indexed uint8 array, hot_x, hot_y) or None.

    res: stored pixels per *screen* pixel, x64 (64 = already at 128x96
    screen scale, 80 = 1.25x finer). File layout:

        4s   'WCS1'
        u8   frame count
        u8   res
        u16  largest frame size in bytes
        per frame: u32 data offset, u8 w, u8 h, i8 hot_x, i8 hot_y
        8-bit pixels, row major
    """
    n = len(frames)
    header = 8 + n * 8
    table = bytearray()
    blob = bytearray()
    biggest = 0
    for fr in frames:
        if fr is None:
            table += struct.pack('<IBBbb', 0, 0, 0, 0, 0)
            continue
        img, hx, hy = fr
        h, w = img.shape
        if w > 255 or h > 255:
            raise ValueError('frame too large for a sprite set: %dx%d'
                             % (w, h))
        hx = max(-128, min(127, hx))
        hy = max(-128, min(127, hy))
        table += struct.pack('<IBBbb', header + len(blob), w, h, hx, hy)
        blob += img.tobytes()
        biggest = max(biggest, w * h)
    with open(path, 'wb') as f:
        f.write(SPRITE_MAGIC)
        f.write(struct.pack('<BBH', n, res, min(biggest, 0xFFFF)))
        f.write(table)
        f.write(blob)
    return header + len(blob)


def write_col_bin(path, indexed_or_rgb, palette=None):
    """Write one full picture in the engine's .COL.bin format
    (u16 w, h, frames, flags + RGB565 rows)."""
    if palette is not None:
        rgb = palette.rgb[indexed_or_rgb].astype(np.uint16)
    else:
        rgb = np.asarray(indexed_or_rgb).astype(np.uint16)
    h, w = rgb.shape[:2]
    v = ((rgb[..., 0] & 0xF8) << 8) | ((rgb[..., 1] & 0xFC) << 3) | \
        (rgb[..., 2] >> 3)
    with open(path, 'wb') as f:
        f.write(struct.pack('<HHHH', w, h, 1, 0))
        f.write(v.astype('<u2').tobytes())


def picture(frame, palette, out_w=128, out_h=96, src_w=320, src_h=200,
            background=(0, 0, 0)):
    """A full-screen shape frame -> (out_h, out_w, 3) RGB array."""
    canvas = np.zeros((src_h, src_w, 4), dtype=np.float32)
    if frame is not None:
        rgba = frame_to_rgba(frame, palette)
        x0 = -frame.left
        y0 = -frame.top
        for y in range(frame.height):
            ty = y + y0
            if 0 <= ty < src_h:
                xs = max(0, -x0)
                xe = min(frame.width, src_w - x0)
                if xe > xs:
                    canvas[ty, x0 + xs:x0 + xe] = rgba[y, xs:xe]
    small = resample(canvas, out_w, out_h)
    alpha = small[..., 3:4]
    bg = np.array(background, dtype=np.float32)
    return np.clip(small[..., :3] + bg * (1 - alpha), 0, 255)
