# wcgfx.py - pixel loops (viper) for the Wing Commander renderer.
#
# All drawing goes into the engine's RGB565 frame buffer
# (display.buffer, 128x128). Sprites are 8-bit indexed in the game
# palette, index 0 = transparent; the palette is a bytearray of 256
# little-endian RGB565 words.
#
# The functions are written so they also run under the CPython
# emulation in thumby_engine.pc (no 32-bit wrap-around tricks, only
# ptr8/ptr16 access on bytearrays, parameters read from a list).


@micropython.viper
def blit_rs(fb, pal, src, sw: int, sh: int, p):
    """Rotated / scaled / flipped sprite blit.

    p (list of ints):
        0,1   cx, cy    where the sprite's hot spot lands on screen
        2,3   hx, hy    hot spot inside the source, 16.16
        4..7  a, b, c, d  inverse matrix, 16.16:
                            u = a*dx + b*dy ; v = c*dx + d*dy
        8..11 x0, y0, x1, y1  destination box, already clipped
    """
    f = ptr16(fb)
    pl = ptr16(pal)
    s = ptr8(src)
    cx = int(p[0]); cy = int(p[1])
    hx = int(p[2]); hy = int(p[3])
    a = int(p[4]); b = int(p[5]); c = int(p[6]); d = int(p[7])
    x0 = int(p[8]); y0 = int(p[9]); x1 = int(p[10]); y1 = int(p[11])
    y = y0
    while y < y1:
        dx = x0 - cx
        dy = y - cy
        u = a * dx + b * dy + hx
        v = c * dx + d * dy + hy
        di = y * 128 + x0
        x = x0
        while x < x1:
            su = u >> 16
            sv = v >> 16
            if su >= 0 and su < sw and sv >= 0 and sv < sh:
                pix = s[sv * sw + su]
                if pix != 0:
                    f[di] = pl[pix]
            u += a
            v += c
            di += 1
            x += 1
        y += 1


@micropython.viper
def blit_indexed(fb, pal, src, x: int, y: int, w: int, h: int,
                 y0: int, y1: int):
    """Unscaled 8-bit picture with transparency; rows clipped to
    [y0, y1), x to the screen."""
    f = ptr16(fb)
    pl = ptr16(pal)
    s = ptr8(src)
    row = 0
    while row < h:
        dy = y + row
        if dy >= y0 and dy < y1:
            si = row * w
            di = dy * 128 + x
            col = 0
            while col < w:
                if x + col >= 0 and x + col < 128:
                    pix = s[si + col]
                    if pix != 0:
                        f[di + col] = pl[pix]
                col += 1
        row += 1


@micropython.viper
def glyph(fb, font, ch: int, x: int, y: int, col: int) -> int:
    """Draw one character of a font<N>.wc file; returns its advance."""
    f = ptr16(fb)
    g = ptr8(font)
    h = int(g[0])
    bpr = int(g[1])
    w = int(g[2 + ch])
    base = 258 + ch * h * bpr
    row = 0
    while row < h:
        dy = y + row
        if dy >= 0 and dy < 128:
            bits = int(g[base + row * bpr])
            if bpr == 2:
                bits = (bits << 8) | int(g[base + row * bpr + 1])
                mask = 0x8000
            else:
                mask = 0x80
            dx = x
            while mask != 0 and bits != 0:
                if (bits & mask) != 0:
                    bits ^= mask
                    if dx >= 0 and dx < 128:
                        f[dy * 128 + dx] = col
                mask >>= 1
                dx += 1
        row += 1
    return w


@micropython.viper
def fill_rows(fb, y0: int, y1: int, col: int):
    f = ptr16(fb)
    i = y0 * 128
    n = y1 * 128
    while i < n:
        f[i] = col
        i += 1


@micropython.viper
def dim_rows(fb, y0: int, y1: int):
    """Halve the brightness of whole rows (menu backdrops)."""
    f = ptr16(fb)
    i = y0 * 128
    n = y1 * 128
    while i < n:
        f[i] = (int(f[i]) >> 1) & 0x7BEF
        i += 1


@micropython.viper
def tint_rows(fb, y0: int, y1: int, col: int):
    """Average rows with a colour (hit flash)."""
    f = ptr16(fb)
    c = (col >> 1) & 0x7BEF
    i = y0 * 128
    n = y1 * 128
    while i < n:
        f[i] = ((int(f[i]) >> 1) & 0x7BEF) + c
        i += 1
