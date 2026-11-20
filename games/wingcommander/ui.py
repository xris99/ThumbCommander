# ui.py - menus and text pages shared by every screen of the game.

from thumby_engine.platform import (display, buttonA, buttonB, buttonU,
                                    buttonD, buttonMENU)
import wcgfx as G

WHITE = 0xFFFF
GREY = 0x8410
DGREY = 0x4208
GREEN = 0x07E0
YELLOW = 0xFFE0
AMBER = 0xFD20
NAVY = 0x0009

small = None        # 6 pixel font
text = None         # 8 pixel font
pal = None          # game palette, 256 RGB565 words (bytearray)
picture = None      # optional backdrop: a 128x96 .COL.bin file name


def setup(small_font, text_font, palette):
    global small, text, pal
    small = small_font
    text = text_font
    pal = palette


def pal565(index):
    return pal[index * 2] | (pal[index * 2 + 1] << 8)


def wait_release():
    """Let go of every button before the next screen reads them."""
    n = 0
    while n < 40 and (buttonA.pressed() or buttonB.pressed() or
                      buttonMENU.pressed()):
        display.update()
        n += 1


def frame_title(title):
    fb = display.buffer
    display.drawFilledRectangle(0, 0, 128, 11, NAVY)
    text.centre(fb, title, 1, AMBER)
    display.drawLine(0, 11, 127, 11, DGREY)


def backdrop(name, y):
    """Draw a converted full picture (assets/<name>) with its top row at
    y. Returns its height, 0 if the file is not there."""
    try:
        f = open('assets/' + name, 'rb')
    except OSError:
        return 0
    head = f.read(8)
    w = head[0] | (head[1] << 8)
    h = head[2] | (head[3] << 8)
    display.draw_open_sprite(f, 0, y, w, h, -1)
    f.close()
    return h


def menu(title, items, sel=0, backdrop_=False, hint=None, pic=None):
    """Pick one of `items` (bytes). Returns the index, or -1 for back.

    backdrop_=True keeps the picture on screen, dimmed, and draws a
    panel over it (the in-flight computer); pic names a converted
    picture to show dimmed behind a full-screen menu. The screen is
    only redrawn when the selection moves - the frame buffer keeps the
    picture between frames."""
    fb = display.buffer
    n = len(items)
    top = 0
    rows = 10
    wait_release()
    if backdrop_:
        G.dim_rows(fb, 0, 128)
        rows = min(n, 9)
    ph = rows * 10 + 18
    py = (128 - ph) // 2 if backdrop_ else 0
    dirty = True
    while True:
        if dirty:
            dirty = False
            if backdrop_:
                display.drawFilledRectangle(6, py, 116, ph, 0)
                display.drawRectangle(6, py, 116, ph, DGREY)
                text.centre(fb, title, py + 3, AMBER)
                y = py + 15
                x = 12
            else:
                display.fill(0)
                if pic and backdrop(pic, 16):
                    G.dim_rows(fb, 16, 112)
                    G.dim_rows(fb, 16, 112)
                frame_title(title)
                y = 16
                x = 4
            if sel < top:
                top = sel
            if sel >= top + rows:
                top = sel - rows + 1
            for i in range(top, min(n, top + rows)):
                if i == sel:
                    display.drawFilledRectangle(
                        x - 2, y - 1, 124 - 2 * (x - 4), 10, 0x0210)
                    text.draw(fb, b'>', x, y, YELLOW)
                text.draw(fb, items[i], x + 8, y,
                          WHITE if i == sel else 0xBDF7)
                y += 10
            if hint and not backdrop_:
                small.centre(fb, hint, 121, GREY)
        display.update()
        if buttonU.justPressed():
            sel = (sel - 1) % n
            dirty = True
        elif buttonD.justPressed():
            sel = (sel + 1) % n
            dirty = True
        elif buttonA.justPressed():
            return sel
        elif buttonB.justPressed() or buttonMENU.justPressed():
            return -1


def page(title, lines, colour=WHITE, hint=b'A: continue'):
    """Show wrapped text; A continues, B / MENU returns False."""
    fb = display.buffer
    out = []
    for ln in lines:
        if ln == b'':
            out.append(b'')
        else:
            out.extend(text.wrap(ln, 122))
    pos = 0
    rows = 11
    wait_release()
    dirty = True
    while True:
        more = pos + rows < len(out)
        if dirty:
            dirty = False
            display.fill(0)
            frame_title(title)
            y = 15
            for ln in out[pos:pos + rows]:
                text.draw(fb, ln, 3, y, colour)
                y += 9
            small.centre(fb, b'A: more' if more else hint, 121, GREY)
        display.update()
        if buttonA.justPressed():
            if more:
                pos += rows
                dirty = True
            else:
                return True
        elif buttonB.justPressed() or buttonMENU.justPressed():
            return False


def message(title, line):
    return page(title, [line])


def wait_key():
    """Hold the current picture until A, B or MENU is pressed."""
    wait_release()
    while True:
        display.update()
        if buttonA.justPressed() or buttonB.justPressed() or \
                buttonMENU.justPressed():
            return


def draw_map(mis, y0, h, px=None, pz=None, dest=-1):
    """Top-down nav map of a mission (the briefing's flight plan):
    the objectives in flight order on the x/z plane, fitted into rows
    y0 .. y0+h. (px, pz) is the player's position in world units."""
    fb = display.buffer
    pts = []
    home = mis.nav_pos(mis.entry_nav if mis.entry_nav >= 0 else 0)
    pts.append((home[0] >> 8, home[2] >> 8, -1))
    for i in range(len(mis.objectives)):
        o = mis.objectives[i]
        if o[0] == 0:
            p = mis.nav_pos(o[1])
        else:
            rec = mis.ship(o[1])
            n = mis.nav_pos(mis.ship_nav[o[1]])
            p = (n[0] + rec[6], 0, n[2] + rec[8])
        pts.append((p[0] >> 8, p[2] >> 8, i))
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    if px is not None:
        xs.append(px)
        zs.append(pz)
    x0 = min(xs); x1 = max(xs); z0 = min(zs); z1 = max(zs)
    span = max(x1 - x0, (z1 - z0) * 108 // max(1, h - 12), 1000)
    cx = (x0 + x1) // 2
    cz = (z0 + z1) // 2
    my = y0 + h // 2

    def sx(x):
        return 64 + (x - cx) * 108 // span

    def sy(z):
        return my - (z - cz) * 108 // span

    display.drawRectangle(2, y0, 124, h, DGREY)
    last = None
    for p in pts:
        x = sx(p[0]); y = sy(p[1])
        if last is not None:
            display.drawLine(last[0], last[1], x, y, 0x2965)
        last = (x, y)
    k = 1
    for p in pts:
        x = sx(p[0]); y = sy(p[1])
        if p[2] == -1:
            display.drawFilledRectangle(x - 2, y - 2, 5, 5, GREEN)
            continue
        o = mis.objectives[p[2]]
        if o[0] == 1:
            continue
        col = YELLOW if p[2] == dest else (GREY if o[3] & 1 else WHITE)
        display.drawRectangle(x - 2, y - 2, 5, 5, col)
        small.draw(fb, str(k).encode(), x + 4, y - 3, col)
        k += 1
    if px is not None:
        x = sx(px); y = sy(pz)
        display.drawLine(x - 3, y, x + 3, y, 0xF81F)
        display.drawLine(x, y - 3, x, y + 3, 0xF81F)
