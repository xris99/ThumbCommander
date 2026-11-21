# flight.py - the cockpit: input, drawing and the flight loop.
#
# Screen layout (128x128): the original 320x200 picture is shown as a
# square-pixel 128x96 picture in rows 16..111; the bars above and below
# carry what would be unreadable at this size inside the cockpit art
# (radio messages, speeds, gun energy, missiles). With the cockpit
# switched off the space view fills rows 0..111.
#
# Projection is the original's (wc1-re src/geom.c
# transform_objects_to_your_view): focal length = half the screen width,
# sprite scale = type scale * 160 / (distance - radius), view picked by
# get_right_shape from 62 directions with mirrored frames.

from thumby_engine.platform import (display, buttonA, buttonB, buttonU,
                                    buttonD, buttonL, buttonR, buttonLB,
                                    buttonRB, buttonMENU, rumble,
                                    audio_play_id)
from array import array
from random import randint
from gc import collect
from time import ticks_ms, ticks_diff, ticks_add
import ui
from math import acos
import wcmath as M
import wcgfx as G
import wcdata as D
import world as W
import ai
import sky

# Game time. One game turn (World.update) is a tenth of a second: the
# original's numbers are per turn and read "times ten per second" - its
# cockpit shows speed * 10 as KPS (wc1-re src/cockpt.c), and the ships'
# turn rates times ten are the degrees per second of the manual. The
# 1990 game ran a turn per frame at whatever the PC managed; Kilrathi
# Saga caps the flight at 20 frames a second and lets the player move
# that cap between 8 and 32 (src/dib.c ReportSpaceFlightMaxFps). Here a
# turn lasts TURN_MS[option 'speed'] by the clock, and frames drawn
# between two turns show the view a fraction of a turn further on.
TURN_MS = (100, 80, 67, 50)
SPEED_NAMES = (b'original', b'1.25x', b'1.5x', b'2x')
# Picture-rate cap in flight. 25, not 30: the firmware rounds the wait
# to whole ms (33) but ticks on the exact period (33.33 ms), and at 30
# the ThumbyColor flickered black under load (device test). 25 = 40 ms.
PICTURES = 25
PACE = True             # False: a turn every frame (the test tools)

PIC_Y = 16              # top row of the 128x96 picture
FX = 64                 # focal length in pixels, horizontal
FY = 77                 # vertical (the original's 1:1.2 pixels)

WHITE = 0xFFFF
GREY = 0x8410
DGREY = 0x4208
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x3DFF
YELLOW = 0xFFE0
ORANGE = 0xFD20

# sprite set per effect type
_BOLT_SET = {24: 'fx06.wcs', 25: 'fx08.wcs', 26: 'fx07.wcs',
             27: 'fx06.wcs'}
_EXPL_SET = ('fx01.wcs', 'fx02.wcs', 'fx03.wcs', 'fx09.wcs')


def num(n):
    return str(n).encode()


def tdiv(a, b):
    """C division (truncates toward zero)."""
    return a // b if a >= 0 else -((-a) // b)


class Flight:
    def __init__(self, types, tables, fonts, pal, state, mission, opts,
                 sfx=False, cache=None, ckbuf=None):
        # cache and ckbuf are the two large buffers of a flight. The game
        # allocates them once at start-up (MainGame) and hands them in;
        # a caller that passes nothing gets fresh ones.
        self.T = types
        self.font = fonts[0]            # small
        self.pal = pal
        self.opts = opts
        self.sfx = sfx
        self.fb = display.buffer
        self.w = W.World(types, tables, mission, state)
        self.brain = ai.Brain(self.w)
        self.w.launch()
        self.sets = {}
        self.ship_names = {}
        self.msg_lines = ()
        if cache is None:
            cache = D.FrameCache()
        cache.reset()
        self.cache = cache
        self.ckbuf = ckbuf
        self.p = [0] * 12               # blit parameters
        self.order = []
        # canonical view frames of the 62 directions (init.c
        # initialize_direction_view_frames): right and up vectors
        self.dirv = array('h', [0] * (62 * 6))
        tmp = [0] * 9
        for idx in range(62):
            if idx == 0:
                yw = 0; pt = 90
            elif idx == 61:
                yw = 0; pt = -90
            else:
                yw = ((idx - 1) % 12) * 30
                pt = 60 - ((idx - 1) // 12) * 30
            M.identity(tmp)
            M.yaw(tmp, yw)
            M.pitch(tmp, pt)
            for k in range(6):
                self.dirv[idx * 6 + k] = min(32767, tmp[k])
        self.cockpit = None
        self.load_cockpit()
        # stars and space dust (sky.py); needs the view set by the cockpit
        self.sky = sky.Sky(self.w.o[0], FX, FY,
                           (self.vx0, self.vy0, self.vx1, self.vy1,
                            self.cx, self.cy))
        self.msg = None
        self.msg_time = 0
        self.b_combo = False
        self.b_held = 0
        # pacing: when the next turn is due, whether this frame ran one,
        # and the view between turns (camera, eye, fraction f / 256)
        sp = opts.get('speed', 0)
        self.turn_ms = TURN_MS[sp if 0 <= sp < len(TURN_MS) else 0]
        self.due = ticks_ms()
        self.t0 = self.due              # for rates()
        self.pictures = 0
        self.turned = True
        self.fr = 256
        self.bk = 0                     # 256 - fr: how far to step back
        self.cam = [0] * 9
        self.ex = self.ey = self.ez = 0
        self.set_view(256)
        # frame times, for the 'WC rate' line
        self.t_last = self.due
        self.slow = 0                   # frames over 50 ms
        self.worst = 0                  # longest frame, ms
        # button events seen since the last turn
        self.l_b = self.l_up = self.l_dn = self.l_a = False
        self.locked = False
        self.auto_blink = 0

    # --- assets ----------------------------------------------------------------
    def load_cockpit(self):
        self.cockpit = None
        self.ck = None
        ship = self.w.o[0].typ
        name = 'ck%d.wc' % ship
        if self.opts.get('cockpit', 1) and D.exists(name):
            if self.ckbuf is None:
                self.ckbuf = bytearray(D.CK_SIZE)
            d = self.ckbuf
            f = open(D.A + name, 'rb')
            n = f.readinto(d)
            f.close()
            if n == len(d):
                self.ck = bytes(d[4:20])
                self.cockpit = memoryview(d)[20:]
        if self.cockpit is not None:
            k = self.ck
            self.vx0 = k[0]; self.vy0 = PIC_Y + k[1]
            self.vx1 = min(128, k[0] + k[2]); self.vy1 = self.vy0 + k[3]
        else:
            self.vx0 = 0; self.vy0 = 0
            self.vx1 = 128; self.vy1 = 112
        self.cx = (self.vx0 + self.vx1) // 2
        self.cy = (self.vy0 + self.vy1) // 2

    def ship_set_name(self, typ):
        n = self.ship_names.get(typ)
        if n is None:
            n = 'sh%02d.wcs' % typ
            self.ship_names[typ] = n
        return n

    def sset(self, name):
        s = self.sets.get(name)
        if s is None:
            if D.exists(name):
                s = D.SpriteSet(name)
            else:
                s = 0
            self.sets[name] = s
        return s

    # --- view ---------------------------------------------------------------------
    def right_shape(self, ob, dx, dy, dz, em, table):
        """get_right_shape -> (frame, flip, clockwise angle)."""
        ox, oy, oz = M.to_frame(ob.m, -dx, -dy, -dz)
        yw, pt = M.spherical(ox, oy, oz)
        q = tdiv(pt, 30)
        rem = pt - q * 30
        band = q + 3
        if rem > 15:
            band = min(band + 1, 6)
        elif rem < -15:
            band = max(band - 1, 0)
        q = tdiv(yw, 30)
        rem = yw - q * 30
        ys = (12 - q) % 12
        if rem > 15:
            ys = (ys + 11) % 12
        elif rem < -15:
            ys = (ys + 1) % 12
        if band <= 0:
            idx = 0
        elif band >= 6:
            idx = 61
        else:
            idx = band * 12 + ys - 11
        eux, euy, euz = M.to_frame(ob.m, em[3], em[4], em[5])
        dv = self.dirv
        b = idx * 6
        px = eux * dv[b] + euy * dv[b + 1] + euz * dv[b + 2]
        py = eux * dv[b + 3] + euy * dv[b + 4] + euz * dv[b + 5]
        ang = M.angle_cw(px >> 8, py >> 8)
        T = self.T
        frame = T.dir_frame[idx + table * 62]
        if frame == 0:
            ang -= 90
        elif frame == 36 and table != 1:
            ang += 90
        return frame, T.dir_flip[idx + table * 62], ang % 360

    def set_view(self, f):
        """Show the world f/256 of the way from the turn before the last
        one to the last one (f = 256: the last turn itself).

        Nothing is guessed: a turn moves every object by its velocity
        after changing it (World.move) and turns the player by its rates
        (rotate_object), so stepping back (256 - f)/256 of that velocity
        and those rates lands exactly between two states the game really
        had. A guess ahead jumps back whenever a rate or a course
        changes; this cannot. The price is that a turn is fully on
        screen one turn later."""
        p = self.w.o[0]
        cam = self.cam
        m = p.m
        for i in range(9):
            cam[i] = m[i]
        self.fr = f
        g = 256 - f
        self.bk = g
        if g > 0:
            if p.rp or p.ry or p.rr:
                M.unturn256(cam, p.rp * g, p.ry * g, p.rr * g)
            self.ex = p.x - ((p.vx * g) >> 8)
            self.ey = p.y - ((p.vy * g) >> 8)
            self.ez = p.z - ((p.vz * g) >> 8)
        else:
            self.ex = p.x
            self.ey = p.y
            self.ez = p.z

    def draw_object(self, ob):
        """Project one object and draw it; fills ob.vis / sx / sy."""
        ob.vis = False
        em = self.cam
        g = self.bk
        dx = (ob.x - ((ob.vx * g) >> 8) - self.ex) >> 8
        dy = (ob.y - ((ob.vy * g) >> 8) - self.ey) >> 8
        dz = (ob.z - ((ob.vz * g) >> 8) - self.ez) >> 8
        if dx > 40000 or dx < -40000 or dz > 40000 or dz < -40000:
            return
        vx, vy, vz = M.to_frame(em, dx, dy, dz)
        if vz < 60:
            return
        dist = M.mag(dx, dy, dz)
        # outside the view cone: skip, unless the object is big enough
        # to reach into the picture from there (a carrier alongside)
        if vz * 256 < dist * 0x94 and ob.radius * 3 < dist:
            return
        sx = self.cx + FX * vx // vz
        sy = self.cy - FY * vy // vz
        ob.sx = sx
        ob.sy = sy
        ob.dist = dist
        c = ob.cls
        typ = ob.typ
        frame = 0
        flip = 0
        ang = 0
        if c >= W.C_SHIP:
            name = self.ship_set_name(typ)
            frame, flip, ang = self.right_shape(
                ob, dx, dy, dz, em, 2 if typ == 21 else 0)
        elif c == W.C_MISSILE:
            name = 'ms.wcs'
            frame, flip, ang = self.right_shape(ob, dx, dy, dz, em, 1)
        elif c == W.C_PROJECTILE:
            name = _BOLT_SET.get(typ, 'fx06.wcs')
        elif c == W.C_EXPLOSION:
            name = _EXPL_SET[min(3, typ - W.OT_EXPLOSION0)]
            frame = ob.counter >> 1
        elif c == W.C_ASTEROID:
            name = 'fx16.wcs' if typ & 1 == 0 else 'fx17.wcs'
            frame = ((self.w.tick >> 1) + ob.counter) % 13
        elif c == W.C_MINE:
            name = 'fx15.wcs'
            frame = (self.w.tick >> 2) % 3
        else:
            return
        # far off screen (the margin grows with the object's projected
        # size, so a big ship is not dropped while its hull still shows)
        mg = 100 + FX * ob.radius // vz
        if sx < self.vx0 - mg or sx > self.vx1 + mg or \
                sy < self.vy0 - mg or sy > self.vy1 + mg:
            return
        ob.vis = self.vx0 <= sx < self.vx1 and self.vy0 <= sy < self.vy1
        dd = dist - ob.radius
        if dd < 1:
            dd = 1
        sset = self.sset(name)
        slot = -1
        if sset:
            slot = self.cache.get(sset, frame)
        fb = self.fb
        if slot < 0:
            if ob.vis:
                display.setPixel(sx, sy, GREY)
            return
        cache = self.cache
        res = cache.res[slot]
        # 16.16 screen scale of the stored frame
        s16 = ((ob.scale * 40 << 8) // (dd * res)) << 8
        cap = (32 * 64 << 16) // res
        if s16 > cap:
            s16 = cap
        w = cache.w[slot]
        h = cache.h[slot]
        hx = cache.hx[slot]
        hy = cache.hy[slot]
        if (max(w, h) * s16) >> 16 < 2 or s16 < 2048:
            # too far to resolve: a point of light
            if ob.vis:
                col = WHITE if c == W.C_PROJECTILE or c == W.C_EXPLOSION \
                    else GREY
                display.setPixel(sx, sy, col)
            return
        ex = max(hx, w - hx)
        ey = max(hy, h - hy)
        rad = ((M.mag(ex, ey, 0) * s16) >> 16) + 2
        x0 = max(self.vx0, sx - rad)
        x1 = min(self.vx1, sx + rad + 1)
        y0 = max(self.vy0, sy - rad)
        y1 = min(self.vy1, sy + rad + 1)
        if x0 >= x1 or y0 >= y1:
            return
        inv = (1 << 24) // (s16 >> 8)          # 16.16 source step
        cs = M.icos(ang)
        sn = M.isin(ang)
        a = ((inv >> 6) * cs) >> 8
        b = ((inv >> 6) * sn) >> 8
        if flip & 1:
            ua = -a; ub = -b
        else:
            ua = a; ub = b
        if flip & 2:
            va = b; vb = -a
        else:
            va = -b; vb = a
        p = self.p
        p[0] = sx; p[1] = sy
        p[2] = (hx << 16) + 0x8000; p[3] = (hy << 16) + 0x8000
        p[4] = ua; p[5] = ub; p[6] = va; p[7] = vb
        p[8] = x0; p[9] = y0; p[10] = x1; p[11] = y1
        G.blit_rs(fb, self.pal, cache.buf[slot], w, h, p)
        ob.rad = rad

    def draw_space(self):
        w = self.w
        fb = self.fb
        G.fill_rows(fb, self.vy0, self.vy1, 0)
        # stars, then the dust; ships are drawn over both
        sk = self.sky
        p = w.o[0]
        sk.draw(fb, display, self.cam, self.ex, self.ey, self.ez, p, True)
        sk.draw(fb, display, self.cam, self.ex, self.ey, self.ez, p, False)
        # far to near
        order = self.order
        del order[:]
        o = w.o
        ex = self.ex; ez = self.ez; ey = self.ey
        for i in range(1, W.NOBJ):
            ob = o[i]
            if ob.cls != W.C_NULL:
                d = abs(ob.x - ex) + abs(ob.y - ey) + abs(ob.z - ez)
                order.append((d, i))
            else:
                ob.vis = False
        order.sort()
        k = len(order) - 1
        while k >= 0:
            self.draw_object(o[order[k][1]])
            k -= 1

    # --- instruments -----------------------------------------------------------
    def bar(self, x, y, w, h, val, full, col):
        display.drawFilledRectangle(x, y, w, h, 0x18E3)
        if full > 0 and val > 0:
            n = min(w, max(1, val * w // full))
            display.drawFilledRectangle(x, y, n, h, col)

    def level_colour(self, val, full):
        if full <= 0 or val * 3 < full:
            return RED
        if val * 3 < full * 2:
            return YELLOW
        return GREEN

    def draw_radar(self, cx, cy, rx, ry):
        w = self.w
        p = w.o[0]
        m = self.cam
        o = w.o
        for i in range(1, W.NOBJ):
            ob = o[i]
            c = ob.cls
            if c < W.C_MISSILE:
                continue
            dx = (ob.x - p.x) >> 8
            dy = (ob.y - p.y) >> 8
            dz = (ob.z - p.z) >> 8
            lx, ly, lz = M.to_frame(m, dx, dy, dz)
            # centre = dead ahead, rim = dead astern
            pl = M.mag(lx, ly, 0)
            off = M.mag(pl, lz, 0)
            if off == 0:
                continue
            ang = int(acos(max(-1.0, min(1.0, lz / off))) * 57.3)
            if pl == 0:
                pl = 1
            x = cx + (lx * ang * rx) // (pl * 180)
            y = cy - (ly * ang * ry) // (pl * 180)
            if c == W.C_MISSILE:
                col = YELLOW
            elif i == p.target and (w.tick & 2):
                col = WHITE
            elif ob.side == W.SIDE_KILRATHI:
                col = RED
            elif c == W.C_CAPITAL:
                col = GREY
            else:
                col = BLUE
            display.setPixel(x, y, col)

    def draw_cockpit(self):
        w = self.w
        p = w.o[0]
        T = self.T.f
        fb = self.fb
        font = self.font
        tg = w.o[p.target] if w.active(p.target) else None
        # gun sight and target brackets (inside the space window)
        cx = self.cx; cy = self.cy
        col = GREEN
        display.drawLine(cx - 5, cy, cx - 2, cy, col)
        display.drawLine(cx + 2, cy, cx + 5, cy, col)
        display.drawLine(cx, cy - 5, cx, cy - 2, col)
        display.drawLine(cx, cy + 2, cx, cy + 5, col)
        if tg is not None and tg.vis:
            r = min(18, max(4, getattr(tg, 'rad', 6)))
            c2 = RED if tg.side == W.SIDE_KILRATHI else BLUE
            x = tg.sx; y = tg.sy
            for sx_, sy_ in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                bx = x + sx_ * r
                by = y + sy_ * r
                if self.vx0 <= bx < self.vx1 and self.vy0 + 2 <= by < self.vy1 - 2:
                    display.drawLine(bx, by, bx - sx_ * 3, by, c2)
                    display.drawLine(bx, by, bx, by - sy_ * 3, c2)
        # destination marker: a small cross where the nav point lies
        if w.dest < len(w.mis.objectives):
            x, y, z = w.objective_pos(w.dest)
            lx, ly, lz = M.to_frame(self.cam, (x - self.ex) >> 8,
                                    (y - self.ey) >> 8, (z - self.ez) >> 8)
            if lz > 0:
                sx = cx + FX * lx // lz
                sy = cy - FY * ly // lz
                if self.vx0 + 2 <= sx < self.vx1 - 2 and \
                        self.vy0 + 2 <= sy < self.vy1 - 2:
                    display.drawLine(sx - 2, sy, sx + 2, sy, WHITE)
                    display.drawLine(sx, sy - 2, sx, sy + 2, WHITE)
        if w.flash:
            G.tint_rows(fb, self.vy0, self.vy1, RED)
        if self.cockpit is not None:
            G.blit_indexed(fb, self.pal, self.cockpit, 0, PIC_Y, 128, 96,
                           PIC_Y, PIC_Y + 96)
            k = self.ck
            self.draw_radar(k[4], PIC_Y + k[5], k[6], k[7])
            lx0 = k[8] + 1; ly0 = PIC_Y + k[9] + 1
            rx0 = k[12] + 1; ry0 = PIC_Y + k[13] + 1
            vw = max(12, k[10] - k[8] - 2)
            display.drawFilledRectangle(lx0, ly0, vw, k[11] - k[9] - 2, 0)
            display.drawFilledRectangle(rx0, ry0, max(12, k[14] - k[12] - 2),
                                        k[15] - k[13] - 2, 0)
        else:
            display.drawFilledRectangle(0, 96, 128, 16, 0)
            self.draw_radar(64, 104, 7, 7)
            display.drawRectangle(56, 96, 17, 16, DGREY)
            lx0 = 2; ly0 = 97; rx0 = 76; ry0 = 97; vw = 50
        # left display: own shields and armour
        self.draw_status(p, lx0, ly0, vw)
        # right display: the target
        if tg is not None:
            name = self.T.names[tg.typ]
            font.draw(fb, name[:6], rx0 + 1, ry0, RED if tg.side == 1
                      else BLUE)
            if self.cockpit is not None:
                self.draw_status(tg, rx0, ry0 + 7, vw)
                rng = w.dist(p, tg)
                font.draw(fb, num(min(99999, rng)), rx0 + 1, ry0 + 25,
                          GREY)
            else:
                self.draw_status(tg, rx0 + 26, ry0 - 1, 22)
        # bottom bar
        y = 113
        display.drawFilledRectangle(0, 112, 128, 16, 0)
        font.draw(fb, b'SET ' + num((p.speed >> 8) * 10), 1, y, GREEN)
        kps = (M.mag(p.vx, p.vy, p.vz) >> 8) * 10
        font.draw(fb, b'KPS ' + num(kps), 44, y,
                  ORANGE if p.special == W.SM_AFTERBURNER else GREEN)
        nm = w.missile_count(p)
        font.draw(fb, b'MSL ' + num(nm), 92, y, YELLOW if nm else DGREY)
        y = 121
        font.draw(fb, b'GUN', 1, y, GREY)
        self.bar(18, y + 1, 24, 4, p.energy, 100, BLUE)
        font.draw(fb, b'FUEL', 46, y, GREY)
        self.bar(66, y + 1, 22, 4, max(0, p.fuel),
                 T[D.T_LIFETIME][p.typ], ORANGE)
        if w.landing_ok:
            font.draw(fb, b'LAND', 96, y, GREEN)
        elif w.autopilot_ok() == 0 and (w.tick & 8):
            font.draw(fb, b'AUTO', 96, y, WHITE)
        # top bar: radio and status messages
        if self.cockpit is not None:
            display.drawFilledRectangle(0, 0, 128, PIC_Y, 0)
        if self.msg is None and w.messages:
            self.msg = w.messages.pop(0)
            self.msg_time = 25              # turns
            self.msg_lines = font.wrap(self.msg[0], 126)[:2]
        if self.msg is not None:
            yy = 1
            for ln in self.msg_lines:
                font.draw(fb, ln, 1, yy, self.msg[1])
                yy += 7
            if self.turned:
                self.msg_time -= 1
            if self.msg_time <= 0:
                self.msg = None
        elif w.dest < len(w.mis.objectives):
            ob = w.mis.objectives[w.dest]
            x, y, z = w.objective_pos(w.dest)
            d = M.mag((x - p.x) >> 8, (y - p.y) >> 8, (z - p.z) >> 8)
            font.draw(fb, ob[2][:30], 1, 1, DGREY)
            font.draw(fb, num(d // 10) + b' klicks', 1, 8, DGREY)

    def draw_status(self, ob, x, y, w):
        """Shield and armour gauges of a ship in a w x 24 box."""
        f = self.T.f
        t = ob.typ
        lc = self.level_colour
        bw = w - 4
        # fore shield / front armour / rear armour / aft shield
        self.bar(x + 2, y + 1, bw, 2, ob.sh[0], f[D.T_SHIELD_F][t], BLUE)
        self.bar(x + 2, y + 5, bw, 3, ob.ar[0], f[D.T_ARMOR_F][t],
                 lc(ob.ar[0], f[D.T_ARMOR_F][t]))
        half = bw // 2 - 1
        self.bar(x + 2, y + 9, half, 3, ob.ar[2], f[D.T_ARMOR_L][t],
                 lc(ob.ar[2], f[D.T_ARMOR_L][t]))
        self.bar(x + 4 + half, y + 9, half, 3, ob.ar[3], f[D.T_ARMOR_RT][t],
                 lc(ob.ar[3], f[D.T_ARMOR_RT][t]))
        self.bar(x + 2, y + 13, bw, 3, ob.ar[1], f[D.T_ARMOR_R][t],
                 lc(ob.ar[1], f[D.T_ARMOR_R][t]))
        self.bar(x + 2, y + 18, bw, 2, ob.sh[1], f[D.T_SHIELD_A][t], BLUE)

    def draw(self):
        self.draw_space()
        self.draw_cockpit()

    # --- input -------------------------------------------------------------------
    def next_target(self):
        """Cycle through the hostile ships, then everything else."""
        w = self.w
        p = w.o[0]
        o = w.o
        start = p.target if p.target > 0 else 0
        for want_enemy in (True, False):
            for k in range(1, W.NSHIP):
                i = (start + k - 1) % (W.NSHIP - 1) + 1
                ob = o[i]
                if ob.cls >= W.C_SHIP and ob.special != W.SM_DYING and \
                        (ob.side == W.SIDE_KILRATHI) == want_enemy:
                    if i != p.target or not want_enemy:
                        p.target = i
                        w.say(b'Target: ' + self.T.names[ob.typ], WHITE)
                        return
        p.target = -1

    def auto_target(self):
        """Without a target, lock the hostile nearest the gun sight."""
        w = self.w
        p = w.o[0]
        if w.active(p.target):
            return
        best = -1
        bf = -200
        for i in range(1, W.NSHIP):
            ob = w.o[i]
            if ob.cls >= W.C_SHIP and ob.side == W.SIDE_KILRATHI and \
                    ob.special != W.SM_DYING:
                w.ship_vs_ship(p, ob)
                if w.FACE > bf:
                    bf = w.FACE
                    best = i
        p.target = best

    def do_autopilot(self):
        w = self.w
        why = w.autopilot_ok()
        if why == 1:
            w.say(b'Autopilot: enemies near', RED)
        elif why == 2:
            w.say(b'Autopilot: hazard near', RED)
        elif not w.autopilot():
            w.say(b'Autopilot: destination reached', YELLOW)
        else:
            self.cache_flush_view()
            ob = w.mis.objectives[w.dest]
            w.say(ob[2], GREEN)

    def cache_flush_view(self):
        for i in range(W.NOBJ):
            self.w.o[i].vis = False

    def latch(self):
        """Note the button events of this frame. Turns come less often
        than frames, and a tap that begins and ends between two turns
        must not be lost; controls() uses up what is noted here."""
        if buttonB.pressed():
            self.l_b = True
            if buttonU.justPressed():
                self.l_up = True
            if buttonD.justPressed():
                self.l_dn = True
        if buttonA.pressed():
            self.l_a = True

    def controls(self):
        """Player input for one turn (HandleSpaceFlightControls)."""
        w = self.w
        p = w.o[0]
        f = self.T.f
        t = p.typ
        up = buttonU.pressed()
        dn = buttonD.pressed()
        lf = buttonL.pressed()
        rt = buttonR.pressed()
        b = buttonB.pressed()
        want_p = 0
        want_y = 0
        want_r = 0
        if b or self.l_b:
            self.b_held += 1
            # B is the shift key: B + d-pad
            if self.l_up:
                self.next_target()
                self.b_combo = True
            if self.l_dn:
                self.do_autopilot()
                self.b_combo = True
        if b:
            if lf:
                want_r = f[D.T_ROLL][t]
                self.b_combo = True
            if rt:
                want_r = -f[D.T_ROLL][t]
                self.b_combo = True
        else:
            if self.b_held and not self.b_combo:
                if w.fire_missile(p) is None:
                    w.say(b'No missile', RED)
            self.b_held = 0
            self.b_combo = False
            inv = -1 if self.opts.get('invert', 0) else 1
            if up:
                want_p = -f[D.T_PITCH][t] * inv
            if dn:
                want_p = f[D.T_PITCH][t] * inv
            if lf:
                want_y = f[D.T_YAW][t]
            if rt:
                want_y = -f[D.T_YAW][t]
        fire = self.l_a or buttonA.pressed()
        self.l_b = self.l_up = self.l_dn = self.l_a = False
        # the stick moves the rates a third of the way each turn
        p.rp += self._ease(p.rp, want_p)
        p.ry += self._ease(p.ry, want_y)
        p.rr += self._ease(p.rr, want_r)
        lb = buttonLB.pressed()
        rb = buttonRB.pressed()
        if lb and rb:
            if p.fuel > 0:
                p.special = W.SM_AFTERBURNER
                p.abtimer = 3
        elif rb:
            w.celerate(p, 0x100)
        elif lb:
            w.celerate(p, -0x100)
        if fire:
            w.fire_guns(p)
        self.auto_target()

    def _ease(self, cur, want):
        d = want - cur
        if d == 0:
            return 0
        step = max(2, abs(d) // 2)
        if d > step:
            return step
        if d < -step:
            return -step
        return d

    # --- loop -----------------------------------------------------------------------
    def frame(self):
        """One picture, and a game turn whenever one is due by the clock
        (see TURN_MS). Returns the flight result (0 while flying).

        If a frame takes longer than a turn, every frame runs one turn
        and the game slows down; it never runs two turns to catch up.
        """
        w = self.w
        self.latch()
        ms = self.turn_ms
        now = ticks_ms()
        dt = ticks_diff(now, self.t_last)
        self.t_last = now
        if 50 < dt < 1000:              # (longer: the flight computer)
            self.slow += 1
            if dt > self.worst:
                self.worst = dt
        late = ticks_diff(now, self.due) if PACE else 0
        if late >= 0:
            if late > ms:               # a pause or a slow frame: start anew
                self.due = ticks_add(self.due, late)
                late = 0
            self.due = ticks_add(self.due, ms)
            self.turned = True
            self.controls()
            w.update()
            self.sky.turn(w.o[0])
            if w.tick % 8 == 0:
                w.check_sphere()
            if w.sfx:
                if self.sfx:
                    audio_play_id(w.sfx[-1])
                del w.sfx[:]
            if w.shake == 3 and rumble and self.opts.get('rumble', 1):
                rumble(40)
            if w.tick % 64 == 0:
                collect()
        else:
            self.turned = False
            late += ms                  # time since the last turn was due
        self.set_view(min(256, late * 256 // ms) if PACE else 256)
        self.draw()
        self.pictures += 1
        return w.result

    def rates(self):
        """(pictures, turns) per second since the flight began, x10.
        Time spent in the flight computer counts, so read it after a
        flight without long pauses."""
        ms = max(1, ticks_diff(ticks_ms(), self.t0))
        return self.pictures * 10000 // ms, self.w.tick * 10000 // ms

    # --- pause menu ------------------------------------------------------------------
    def pause(self):
        """In-flight computer. Returns a flight result (0 = keep flying)."""
        w = self.w
        p = w.o[0]
        sel = 0
        while True:
            self.draw()
            sel = ui.menu(b'FLIGHT COMPUTER', [
                b'Resume', b'Autopilot', b'Nav map', b'Communications',
                b'Guns', b'Missiles',
                b'Cockpit: on' if self.opts.get('cockpit', 1)
                else b'Cockpit: off',
                b'Eject', b'Abort mission'], sel, True)
            if sel <= 0:
                return 0
            if sel == 1:
                self.do_autopilot()
                return 0
            if sel == 2:
                self.nav_map()
            elif sel == 3:
                if self.comm():
                    return 0
            elif sel == 4:
                self.select_weapons(W.C_PROJECTILE, b'GUNS')
            elif sel == 5:
                self.select_weapons(W.C_MISSILE, b'MISSILES')
            elif sel == 6:
                self.opts['cockpit'] = 0 if self.opts.get('cockpit', 1) else 1
                self.load_cockpit()
            elif sel == 7:
                self.draw()
                if ui.menu(b'EJECT?', [b'No', b'Yes, eject'], 0, True) == 1:
                    return W.R_EJECTED
            elif sel == 8:
                self.draw()
                if ui.menu(b'ABORT?', [b'No', b'Yes, give up'], 0,
                           True) == 1:
                    return W.R_ABORT

    def nav_map(self):
        w = self.w
        p = w.o[0]
        fb = self.fb
        display.fill(0)
        ui.frame_title(b'NAV MAP')
        ui.draw_map(w.mis, 13, 62, p.x >> 8, p.z >> 8, w.dest)
        y = 78
        objs = w.mis.objectives
        for i in range(min(6, len(objs))):
            o = objs[i]
            col = ui.GREEN if o[3] & 1 else \
                (ui.YELLOW if i == w.dest else 0xBDF7)
            self.font.draw(fb, o[2][:31], 3, y, col)
            y += 7
        ui.wait_key()

    def comm(self):
        """Orders for the wingman and the landing request."""
        w = self.w
        self.draw()
        k = ui.menu(b'COMMUNICATIONS', [
            b'Break and attack', b'Form on my wing', b'Attack my target',
            b'Request landing'], 0, True)
        if k < 0:
            return False
        wm = w.o[w.wingman] if w.wingman >= 0 else None
        if k == 3:
            home = w.find_ship(w.mis.home_ship)
            if home < 0 or w.dist(w.o[0], w.o[home]) > 12000:
                w.say(b'No carrier in range', RED)
            elif w.enemies_left():
                w.say(b'Negative, hostiles in the area', RED)
            else:
                w.landing_ok = True
                w.say(b'Cleared to land', GREEN)
            return True
        if wm is None or not w.active(w.wingman):
            w.say(b'No wingman', RED)
            return True
        if k == 0:
            w.engage_ok = True
        elif k == 1:
            w.engage_ok = False
        else:
            w.engage_ok = True
            if w.active(w.o[0].target):
                wm.target = w.o[0].target
                wm.objective = ai.O_ENGAGE
        self.brain.message(wm, 0)
        return True

    def select_weapons(self, cls, title):
        """Choose which guns fire together / which missile goes next."""
        p = self.w.o[0]
        f = self.T.f
        while True:
            idx = [k for k in range(len(p.weapons))
                   if f[D.T_CLASS][p.weapons[k][0]] == cls]
            if not idx:
                self.w.say(b'None left', RED)
                return
            items = []
            for k in idx:
                wpn = p.weapons[k]
                items.append((b'[ ] ' if wpn[2] else b'[x] ') +
                             self.T.names[wpn[0]][:14])
            self.draw()
            k = ui.menu(title, items, 0, True)
            if k < 0:
                return
            wpn = p.weapons[idx[k]]
            if cls == W.C_MISSILE:
                # the chosen type becomes the next one off the rail
                for j in idx:
                    p.weapons[j][2] = 0 if p.weapons[j][0] == wpn[0] else 1
                return
            wpn[2] ^= 1
