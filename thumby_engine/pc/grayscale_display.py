# thumby_engine.pc.grayscale_display
#
# CPython/pygame port of the original-Thumby grayscale display driver
# (thumby_engine.display.grayscale - an RP2040 SPI/OLED driver that can
# not run on a PC). It is registered into sys.modules under the firmware
# module name `thumby_engine.display.grayscale` by
# thumby_engine.pc.bootstrap(mode='thumby'), so thumby_engine.platform
# takes its *original-Thumby* branch and picks this implementation up
# transparently - the engine and game source run unmodified.
#
# Faithfulness notes:
#   * Bitplane model is 1:1 with the hardware: two 1bpp column-major page
#     planes (light plane + shading plane, 72 bytes per page, 5 pages for
#     40 rows). Level value = bit0 (light) | bit1 (shading) ->
#     BLACK=0 WHITE=1 DARKGRAY=2 LIGHTGRAY=3.
#   * The hardware composes grays by temporal subframe dithering
#     (WHITE 3/3 subframes on, LIGHTGRAY 2/3, DARKGRAY 1/3, BLACK off).
#     On a PC that is displayed as the equivalent static grays
#     0/85/170/255 (see thumby_engine.pc.engine_draw).
#   * All drawing routines are direct ports of the hardware viper code -
#     same clipping, same page-mask arithmetic, same key/mirror semantics.
#   * Fonts: the Thumby branch asks for '/lib/fontNNN.bin', which only
#     exists inside the device firmware. On the PC a present, non-empty
#     requested file is used verbatim (matching what would be deployed);
#     otherwise resolution falls back to the vendored real firmware fonts
#     in this package's fonts/ directory, and only as a last resort to a
#     font derived from the built-in 8x8 FONT_DATA.
#   * Thumby-mode pacing emulates the device's render cost: the real
#     Thumby is render-bound (a bitplane push plus temporal-dither
#     subframes costs far more than the PC window blit), so scenes whose
#     frame period is below that cost run slower than their setFPS target
#     on the device (flight 40 -> ~10 fps). Grayscale.update() sleeps that
#     cost after blitting; override via THUMBY_DEVICE_RENDER_MS (= 0
#     restores full target speed on the PC).

import os
import time
from os import stat

from . import engine
from . import engine_draw
from . import utime
from .framebuf import FONT_DATA
from ..util.fpmath import fpmul, fpdiv

_WIDTH = 72
_HEIGHT = 40
_BUFF_SIZE = (_HEIGHT // 8) * _WIDTH  # 360 bytes per bitplane

_BLACK, _WHITE, _DARKGRAY, _LIGHTGRAY = 0, 1, 2, 3


def _default_scale():
    """Window magnification for the 72x40 panel (default 6 -> 432x240)."""
    try:
        return max(1, int(os.environ.get('THUMBY_SCALE', '6')))
    except ValueError:
        return 6


# --- Emulated device render cost ------------------------------------------
# The real Thumby spends most of a frame pushing the two bitplanes plus
# the temporal-dither subframes - far slower than the PC's window blit -
# so render-bound scenes run below their setFPS target on the device
# (flight 40 -> ~10 fps, menu 30 -> ~10 fps), while scenes whose frame
# period already exceeds the cost (game-over, cutscenes, the 8 fps intro)
# are unaffected. Grayscale.update() sleeps this cost after each blit to
# reproduce that effective frame rate on the PC. Default 100ms; override
# via THUMBY_DEVICE_RENDER_MS (= 0 disables the emulation and restores
# full target speed).
def _device_render_ms():
    try:
        return max(0.0, float(os.environ.get('THUMBY_DEVICE_RENDER_MS',
                                            '100')))
    except ValueError:
        return 100.0


_DEVICE_RENDER_MS = _device_render_ms()


# --- Firmware fonts -------------------------------------------------------
# fonts/ in this package holds the real firmware font files
# (font3x5.bin / font5x7.bin / font8x8.bin, taken from CoreThumbyFiles/lib
# of the official TinyCircuits Thumby code-editor simulator; font5x7 is
# byte-identical to the copy bundled by samclane/Thumbox). The layout is
# exactly what drawText() consumes: width bytes per glyph (one per column),
# bit r = row r, bit0 = top row, 96 glyphs for ASCII 0x20..0x7F.
# The built-in fallback font is 8x8 (framebuf.FONT_DATA); smaller sizes are
# downsampled from it with ink-preserving OR-blocks only when no real font
# file is available at all.

def _groups(src_n, dst_n):
    """Partition src_n source units into dst_n non-empty ceil groups."""
    out = []
    start = 0
    for j in range(dst_n):
        end = -(-(j + 1) * src_n // dst_n)   # ceil((j+1)*src_n/dst_n)
        out.append((start, end))
        start = end
    return out


def _derive_font(width, height):
    """Derive a firmware-layout font of width x height from FONT_DATA."""
    cols = _groups(8, width)
    rows = _groups(8, height)
    out = bytearray()
    for i in range(96):
        for c0, c1 in cols:
            byte = 0
            for r, (r0, r1) in enumerate(rows):
                ink = False
                for sc in range(c0, c1):
                    col = FONT_DATA[i * 8 + sc]
                    for sr in range(r0, r1):
                        if (col >> sr) & 1:
                            ink = True
                            break
                    if ink:
                        break
                if ink:
                    byte |= 1 << r
            out.append(byte)
    return bytes(out)


_PKG_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'fonts')


def _try_font_file(path):
    """Read a font file into a bytearray; return None when it is absent,
    empty or an all-zero placeholder (a placeholder carries no ink - the
    shipped game font assets are exactly that)."""
    try:
        sz = stat(path)[6]
    except OSError:
        return None
    if sz == 0:
        return None
    try:
        data = bytearray(sz)
        with open(path, 'rb') as fh:
            fh.readinto(data)
    except OSError:
        return None
    return data if any(data) else None


def _resolve_font_bytes(path, width, height):
    """Resolve font bytes for setFont. First hit wins:

      1. the requested path verbatim - what would be deployed to the
         device when a real (non-placeholder) font file is present;
      2. the file's basename in the game directory (bootstrap() chdirs
         there) and under its assets/ folder;
      3. the vendored real firmware fonts in this package's fonts/
         directory - these are the '/lib/fontNNN.bin' files a PC cannot
         see any other way;
      4. last resort: a firmware-layout font derived from the built-in
         8x8 FONT_DATA (ink-preserving OR-block downsampling).
    """
    data = _try_font_file(path)
    if data is None:
        name = os.path.basename(path)
        for cand in (name, os.path.join('assets', name),
                     os.path.join(_PKG_FONT_DIR, name)):
            data = _try_font_file(cand)
            if data is not None:
                break
    if data is None:
        if width < 1 or height < 1:
            raise ValueError('font dimensions must be >= 1')
        print(f"[Grayscale-PC] font '{path}' unavailable/empty - using "
              f"derived {width}x{height} firmware-style fallback", flush=True)
        data = bytearray(_derive_font(width, height))
    return data


class Sprite:
    """1-bit sprite with optional shading plane. Layout:
    width * ceil(height/8) bytes, column-major page order."""

    def __init__(self, width, height, bitmapData, x=0, y=0, key=-1,
                 mirrorX=False, mirrorY=False):
        self.width = width
        self.height = height
        self.scaledWidth = width
        self.scaledHeight = height
        self.scale = 1 << 16
        self.bitmapSource = bitmapData
        self.bitmapByteCount = width * (height // 8)
        if height % 8:
            self.bitmapByteCount += width
        self.frameCount = 1
        self.currentFrame = 0
        self._shaded = False
        self._usesFile = False
        if isinstance(bitmapData, (tuple, list)):
            if (len(bitmapData) != 2) or (type(bitmapData[0]) != type(bitmapData[1])):
                raise ValueError('bitmapData must be a bytearray, string, '
                                 'or tuple of two bytearrays or strings')
            self._shaded = True
            if isinstance(bitmapData[0], str):
                self._usesFile = True
                if stat(bitmapData[0])[6] != stat(bitmapData[1])[6]:
                    raise ValueError('Sprite files must match in size')
                self.bitmap = (bytearray(self.bitmapByteCount),
                               bytearray(self.bitmapByteCount))
                self.files = (open(bitmapData[0], 'rb'),
                              open(bitmapData[1], 'rb'))
                self.files[0].readinto(self.bitmap[0])
                self.files[1].readinto(self.bitmap[1])
                self.frameCount = stat(bitmapData[0])[6] // self.bitmapByteCount
            elif isinstance(bitmapData[0], bytearray):
                if len(bitmapData[0]) != len(bitmapData[1]):
                    raise ValueError('Sprite bitplanes must match in size')
                self.frameCount = len(bitmapData[0]) // self.bitmapByteCount
                self.bitmap = [
                    memoryview(bitmapData[0])[0:self.bitmapByteCount],
                    memoryview(bitmapData[1])[0:self.bitmapByteCount]
                ]
            else:
                raise ValueError('bitmapData must be a bytearray, string, '
                                 'or tuple of two bytearrays or strings')
        elif isinstance(bitmapData, str):
            self._usesFile = True
            self.bitmap = bytearray(self.bitmapByteCount)
            self.file = open(bitmapData, 'rb')
            self.file.readinto(self.bitmap)
            self.frameCount = stat(bitmapData)[6] // self.bitmapByteCount
        elif isinstance(bitmapData, bytearray):
            self.bitmap = memoryview(bitmapData)[0:self.bitmapByteCount]
            self.frameCount = len(bitmapData) // self.bitmapByteCount
        else:
            raise ValueError('bitmapData must be a bytearray, string, '
                             'or tuple of two bytearrays or strings')
        self.x = x
        self.y = y
        self.key = key
        self.mirrorX = mirrorX
        self.mirrorY = mirrorY

    def getFrame(self):
        return self.currentFrame

    def setFrame(self, frame):
        if frame >= 0 and (self.currentFrame is not frame % (self.frameCount)):
            self.currentFrame = frame % (self.frameCount)
            offset = self.bitmapByteCount * self.currentFrame
            if self._shaded:
                if self._usesFile:
                    self.files[0].seek(offset)
                    self.files[1].seek(offset)
                    self.files[0].readinto(self.bitmap[0])
                    self.files[1].readinto(self.bitmap[1])
                else:
                    self.bitmap[0] = memoryview(self.bitmapSource[0])[
                        offset:offset + self.bitmapByteCount]
                    self.bitmap[1] = memoryview(self.bitmapSource[1])[
                        offset:offset + self.bitmapByteCount]
            else:
                if self._usesFile:
                    self.file.seek(offset)
                    self.file.readinto(self.bitmap)
                else:
                    self.bitmap = memoryview(self.bitmapSource)[
                        offset:offset + self.bitmapByteCount]

    def setScale(self, scale: int):
        self.scale = scale
        self.scaledWidth = fpmul(self.width << 16, scale) >> 16
        self.scaledHeight = fpmul(self.height << 16, scale) >> 16

    def setLifes(self, lifes: int):
        self.lifes = lifes

    def getLifes(self) -> int:
        return self.lifes


class Grayscale:
    """Original-Thumby display: 72x40, two 1bpp bitplanes -> 4 levels.
    API-compatible drop-in for the hardware Grayscale class."""

    BLACK = _BLACK
    WHITE = _WHITE
    DARKGRAY = _DARKGRAY
    LIGHTGRAY = _LIGHTGRAY

    def __init__(self):
        self.display = self  # hardware parity: GraphicsClass == display
        self.pages = _HEIGHT // 8
        self.width = _WIDTH
        self.height = _HEIGHT
        self.max_x = _WIDTH - 1
        self.max_y = _HEIGHT - 1

        self.drawBuffer = bytearray(_BUFF_SIZE * 2)
        self.buffer = memoryview(self.drawBuffer)[:_BUFF_SIZE]
        self.shading = memoryview(self.drawBuffer)[_BUFF_SIZE:]

        self._brightness = 127
        self._contrast = bytearray(3)
        self._invert = 0
        self._pendingCmds = bytearray(8)

        self.setFont('/lib/font5x7.bin', 5, 7, 1)

        self.lastUpdateEnd = 0
        self.frameRate = 0

    # --- SSD1306-ish compatibility stubs (no hardware on a PC) ----------
    def __enter__(self):
        self.enableGrayscale()
        return self

    def __exit__(self, type, value, traceback):
        self.disableGrayscale()

    def enableGrayscale(self):
        pass

    def disableGrayscale(self):
        pass

    def reset(self):
        pass

    def init_display(self):
        pass

    def write_cmd(self, cmd):
        pass

    def poweroff(self):
        pass

    def poweron(self):
        pass

    def invert(self, invert: int):
        self._invert = 1 if invert else 0

    def brightness(self, c: int):
        if c < 1:
            c = 1
        if c > 127:
            c = 127
        self._brightness = c

    # --- frame push ------------------------------------------------------
    def show(self):
        fb = engine_draw.back_fb(width=_WIDTH, height=_HEIGHT,
                                 scale=_default_scale(), grayscale=True)
        fb.blit_grayscale(self.buffer, self.shading, self._invert)

    def show_async(self):
        self.show()

    def setFPS(self, newFrameRate):
        self.frameRate = newFrameRate
        # Same pacer the ThumbyColor display uses on the PC: the engine
        # enforces the frame period and polls the keyboard once per tick.
        engine.fps_limit(newFrameRate)

    def update(self):
        self.show()
        if _DEVICE_RENDER_MS > 0:
            # emulate the device's per-frame bitplane push cost (see
            # _device_render_ms above) before completing the frame period
            time.sleep(_DEVICE_RENDER_MS / 1000.0)
        if self.frameRate > 0:
            # Complete the frame period, then let the engine tick: it
            # re-enforces the pace boundary (no-op here, we just waited)
            # and samples the keyboard - the single per-frame input poll.
            while engine.time_to_next_tick() > 0:
                pass
            engine.tick()
        else:
            # Scenes that never call setFPS (the title attract loop)
            # schedule no engine tick, so the tick-based keyboard poll
            # above would never run and the keyboard would appear frozen.
            # The device's buttons are IRQ-driven - live state without
            # ticks - so mirror that here: sample once per frame.
            if engine.update_button_state is not None:
                engine.update_button_state()
        self.lastUpdateEnd = utime.ticks_ms()

    # --- GraphicsClass (direct ports of the hardware viper routines) ----
    def fill(self, colour: int):
        f1 = 0xFF if colour & 1 else 0
        f2 = 0xFF if colour & 2 else 0
        self.buffer[:] = bytes([f1]) * _BUFF_SIZE
        self.shading[:] = bytes([f2]) * _BUFF_SIZE

    def drawFilledRectangle(self, x: int, y: int, width: int, height: int,
                            colour: int):
        if x + width <= 0 or x >= _WIDTH or y + height <= 0 or y >= _HEIGHT:
            return
        if width <= 0 or height <= 0:
            return
        if x < 0:
            width += x
            x = 0
        if y < 0:
            height += y
            y = 0
        x2 = x + width
        y2 = y + height
        if x2 > _WIDTH:
            x2 = _WIDTH
            width = _WIDTH - x
        if y2 > _HEIGHT:
            y2 = _HEIGHT
            height = _HEIGHT - y

        buffer = self.buffer
        shading = self.shading

        o = (y >> 3) * _WIDTH
        oe = o + x2
        o += x
        strd = _WIDTH - width

        c1 = colour & 1
        c2 = colour & 2
        v1 = 0xff if c1 else 0
        v2 = 0xff if c2 else 0

        yb = y & 7
        ybh = 8 - yb
        if height <= ybh:
            m = ((1 << height) - 1) << yb
        else:
            m = 0xff << yb
        im = 255 - m
        # Viper stores via ptr8, so every read-modify-write is truncated
        # to one byte: (x | m) & 0xff == x | (m & 0xff), and for the wide
        # top mask (m > 0xff, im negative) (x & im) & 0xff keeps exactly
        # the bits below yb - the same byte math the hardware performs.
        while o < oe:
            if c1:
                buffer[o] = (buffer[o] | m) & 0xff
            else:
                buffer[o] = (buffer[o] & im) & 0xff
            if c2:
                shading[o] = (shading[o] | m) & 0xff
            else:
                shading[o] = (shading[o] & im) & 0xff
            o += 1
        height -= ybh
        while height >= 8:
            o += strd
            oe += _WIDTH
            while o < oe:
                buffer[o] = v1
                shading[o] = v2
                o += 1
            height -= 8
        if height > 0:
            o += strd
            oe += _WIDTH
            m = (1 << height) - 1
            im = 255 - m
            while o < oe:
                if c1:
                    buffer[o] |= m
                else:
                    buffer[o] &= im
                if c2:
                    shading[o] |= m
                else:
                    shading[o] &= im
                o += 1

    def drawRectangle(self, x: int, y: int, width: int, height: int,
                      colour: int):
        dfr = self.drawFilledRectangle
        dfr(x, y, width, 1, colour)
        dfr(x, y, 1, height, colour)
        dfr(x, y + height - 1, width, 1, colour)
        dfr(x + width - 1, y, 1, height, colour)

    def setPixel(self, x: int, y: int, colour: int):
        if x < 0 or x >= _WIDTH or y < 0 or y >= _HEIGHT:
            return
        o = (y >> 3) * _WIDTH + x
        m = 1 << (y & 7)
        im = 255 - m
        buffer = self.buffer
        shading = self.shading
        if colour & 1:
            buffer[o] |= m
        else:
            buffer[o] &= im
        if colour & 2:
            shading[o] |= m
        else:
            shading[o] &= im

    def getPixel(self, x: int, y: int) -> int:
        if x < 0 or x >= _WIDTH or y < 0 or y >= _HEIGHT:
            return 0
        o = (y >> 3) * _WIDTH + x
        m = 1 << (y & 7)
        buffer = self.buffer
        shading = self.shading
        colour = 0
        if buffer[o] & m:
            colour = 1
        if shading[o] & m:
            colour |= 2
        return colour

    def drawLine(self, x0: int, y0: int, x1: int, y1: int, colour: int):
        if x0 == x1:
            self.drawFilledRectangle(x0, y0, 1, y1 - y0, colour)
            return
        if y0 == y1:
            self.drawFilledRectangle(x0, y0, x1 - x0, 1, colour)
            return
        dx = x1 - x0
        dy = y1 - y0
        sx = 1
        if dy < 0:
            x0, x1 = x1, x0
            y0, y1 = y1, y0
            dy = 0 - dy
            dx = 0 - dx
        if dx < 0:
            dx = 0 - dx
            sx = -1
        x = x0
        y = y0
        buffer = self.buffer
        shading = self.shading

        o = (y >> 3) * _WIDTH + x
        m = 1 << (y & 7)
        im = 255 - m
        c1 = colour & 1
        c2 = colour & 2

        if dx > dy:
            err = dx >> 1
            x1 += 1
            while x != x1:
                if 0 <= x < _WIDTH and 0 <= y < _HEIGHT:
                    if c1:
                        buffer[o] |= m
                    else:
                        buffer[o] &= im
                    if c2:
                        shading[o] |= m
                    else:
                        shading[o] &= im
                err -= dy
                if err < 0:
                    y += 1
                    m <<= 1
                    if m & 0x100:
                        o += _WIDTH
                        m = 1
                        im = 0xfe
                    else:
                        im = 255 - m
                    err += dx
                x += sx
                o += sx
        else:
            err = dy >> 1
            y1 += 1
            while y != y1:
                if 0 <= x < _WIDTH and 0 <= y < _HEIGHT:
                    if c1:
                        buffer[o] |= m
                    else:
                        buffer[o] &= im
                    if c2:
                        shading[o] |= m
                    else:
                        shading[o] &= im
                err -= dx
                if err < 0:
                    x += sx
                    o += sx
                    err += dy
                y += 1
                m <<= 1
                if m & 0x100:
                    o += _WIDTH
                    m = 1
                    im = 0xfe
                else:
                    im = 255 - m

    # --- fonts -----------------------------------------------------------
    def setFont(self, fontFile, width, height, space):
        data = _resolve_font_bytes(fontFile, width, height)
        self.font_bmap = data
        self.font_width = width
        self.font_height = height
        self.font_space = space
        self.font_glyphcnt = len(data) // width

    def drawText(self, stringToPrint, x: int, y: int, colour: int):
        buffer = self.buffer
        shading = self.shading
        font_bmap = self.font_bmap
        font_width = self.font_width
        font_space = self.font_space
        font_glyphcnt = self.font_glyphcnt
        sm1o = 0xff if colour & 1 else 0
        sm1a = 255 - sm1o
        sm2o = 0xff if colour & 2 else 0
        sm2a = 255 - sm2o
        ou = (y >> 3) * _WIDTH + x
        ol = ou + _WIDTH
        shu = y & 7
        shl = 8 - shu
        for c in stringToPrint:
            if isinstance(c, str):
                co = int(ord(c)) - 0x20
            else:
                co = int(c) - 0x20
            if co < font_glyphcnt:
                gi = co * font_width
                gx = 0
                while gx < font_width:
                    if 0 <= x < _WIDTH:
                        gb = font_bmap[gi + gx]
                        gbu = gb << shu
                        gbl = gb >> shl
                        if 0 <= ou < _BUFF_SIZE:
                            # paint upper byte
                            buffer[ou] = (buffer[ou] | (gbu & sm1o)) \
                                & 255 - (gbu & sm1a)
                            shading[ou] = (shading[ou] | (gbu & sm2o)) \
                                & 255 - (gbu & sm2a)
                        if (shl != 8) and (0 <= ol < _BUFF_SIZE):
                            # paint lower byte
                            buffer[ol] = (buffer[ol] | (gbl & sm1o)) \
                                & 255 - (gbl & sm1a)
                            shading[ol] = (shading[ol] | (gbl & sm2o)) \
                                & 255 - (gbl & sm2a)
                    ou += 1
                    ol += 1
                    x += 1
                    gx += 1
            ou += font_space
            ol += font_space
            x += font_space

    # --- blits -----------------------------------------------------------
    def blit(self, src, x: int, y: int, width: int, height: int, key: int,
             mirrorX: int, mirrorY: int):
        if x + width < 0 or x >= _WIDTH:
            return
        if y + height < 0 or y >= _HEIGHT:
            return
        buffer = self.buffer
        shading = self.shading

        if isinstance(src, (tuple, list)):
            shd = 1
            src1 = src[0]
            src2 = src[1]
        else:
            shd = 0
            src1 = src
            src2 = None

        stride = width

        srcx = 0
        srcy = 0
        dstx = x
        dsty = y
        sdx = 1
        if mirrorX:
            sdx = -1
            srcx += width - 1
            if dstx < 0:
                srcx += dstx
                width += dstx
                dstx = 0
        else:
            if dstx < 0:
                srcx = 0 - dstx
                width += dstx
                dstx = 0
        if dstx + width > _WIDTH:
            width = _WIDTH - dstx
        if mirrorY:
            srcy = height - 1
            if dsty < 0:
                srcy += dsty
                height += dsty
                dsty = 0
        else:
            if dsty < 0:
                srcy = 0 - dsty
                height += dsty
                dsty = 0
        if dsty + height > _HEIGHT:
            height = _HEIGHT - dsty

        srco = (srcy >> 3) * stride + srcx
        srcm = 1 << (srcy & 7)

        dsto = (dsty >> 3) * _WIDTH + dstx
        dstm = 1 << (dsty & 7)
        dstim = 255 - dstm

        while height != 0:
            srcco = srco
            dstco = dsto
            i = width
            while i != 0:
                v = 0
                if src1[srcco] & srcm:
                    v = 1
                if shd and (src2[srcco] & srcm):
                    v |= 2
                if (key == -1) or (v != key):
                    if v & 1:
                        buffer[dstco] |= dstm
                    else:
                        buffer[dstco] &= dstim
                    if v & 2:
                        shading[dstco] |= dstm
                    else:
                        shading[dstco] &= dstim
                srcco += sdx
                dstco += 1
                i -= 1
            dstm <<= 1
            if dstm & 0x100:
                dsto += _WIDTH
                dstm = 1
                dstim = 0xfe
            else:
                dstim = 255 - dstm
            if mirrorY:
                srcm >>= 1
                if srcm == 0:
                    srco -= stride
                    srcm = 0x80
            else:
                srcm <<= 1
                if srcm & 0x100:
                    srco += stride
                    srcm = 1
            height -= 1

    def drawSprite(self, s):
        self.blit(s.bitmap, s.x, s.y, s.width, s.height, s.key, s.mirrorX,
                  s.mirrorY)

    def blitScaled(self, src, x: int, y: int, width: int, height: int,
                   key: int, mirrorX: int, mirrorY: int, scale: int,
                   realWidth: int):
        if x + width < 0 or x > _WIDTH - 1:
            return
        if y + height < 0 or y > _HEIGHT - 1:
            return
        buffer = self.buffer
        shading = self.shading

        if isinstance(src, (tuple, list)):
            shd = 1
            src1 = src[0]
            src2 = src[1]
        else:
            shd = 0
            src1 = src
            src2 = None

        xStart = int(x)
        yStart = int(y)

        yFirst = 0 - yStart
        blitHeight = height
        if yFirst < 0:
            yFirst = 0
        if yStart + height > _HEIGHT:
            blitHeight = _HEIGHT - yStart
        y = yFirst

        xFirst = 0 - xStart
        blitWidth = width
        if xFirst < 0:
            xFirst = 0
        if xStart + width > _WIDTH:
            blitWidth = _WIDTH - xStart

        while y < blitHeight:
            x = xFirst
            while x < blitWidth:
                sy = (((height - 1 - y) if mirrorY == 1 else y) * scale) >> 8
                sx = (((width - 1 - x) if mirrorX == 1 else x) * scale) >> 8

                i = (sy >> 3) * realWidth + sx
                pixel_pos = ((yStart + y) >> 3) * _WIDTH + xStart + x
                bit_pos = 1 << ((yStart + y) & 0x07)

                # Determine the color (0-3) based on both buffers
                color = 0
                if src1[i] & (1 << (sy & 0x07)):
                    color |= 1
                if shd == 1 and (src2[i] & (1 << (sy & 0x07))):
                    color |= 2

                if color != key:
                    if color & 1:
                        buffer[pixel_pos] |= bit_pos
                    else:
                        buffer[pixel_pos] &= 0xff ^ bit_pos
                    if shd == 1:
                        if color & 2:
                            shading[pixel_pos] |= bit_pos
                        else:
                            shading[pixel_pos] &= 0xff ^ bit_pos
                x += 1
            y += 1

    def drawSpriteWithScale(self, s):
        self.blitScaled(s.bitmap, s.x, s.y, s.scaledWidth, s.scaledHeight,
                        s.key, s.mirrorX, s.mirrorY,
                        fpdiv(256 << 16, s.scale) >> 16, s.width)


def create_sprite(width, height, bitmap_data, x=0, y=0, key=-1,
                  mirrorX=False, mirrorY=False, cWidth=0, cHeight=0):
    """1-bit (BIT + SHD) sprite. `bitmap_data` is a bytearray pair, or a
    (bit_path, shd_path) tuple loaded from files."""
    return Sprite(width, height, bitmap_data, x, y, key, mirrorX, mirrorY)

# NOTE: the display instance is created by thumby_engine.platform
# (one instance per running program); this module only provides the
# Grayscale/Sprite classes and the helpers above.
