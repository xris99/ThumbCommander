# sky.py - the backdrop of a flight: space dust and stars.
#
# Behaviour follows the original (wc1-re src/spc.c update_star_field,
# start_dust; src/geom.c); the specks
# are plain pixels and streaks:
#
# - Dust: 15 specks in space. One that is behind the ship, outside the
#   view, nearer than the ship's radius or further than 1400 units is
#   placed ahead again with chance 2/8 per turn: at a distance that grows
#   with the forward speed, off the axis by up to half that distance, led
#   by ten turns of the ship's sideways motion. They stand still, so the
#   ship flies through them. This port draws each as a streak from where
#   it was half a turn ago, so the speed shows.
# - Stars: directions only (no parallax). A star that leaves the view is
#   put back just beyond the edge the view is turning towards (the
#   original uses 45 degrees on the turning axis and a random angle on
#   the other). Here every lost star returns in the same turn, between
#   the edge and one turn's rotation beyond it, and the random angle
#   stays inside the view, so the field stays full while turning.

from array import array
from random import randint
from math import atan
import wcmath as M

NDUST = 15
NSTAR = 26
DUST_FAR = 1400

WHITE = 0xFFFF
LGREY = 0xC618
GREY = 0x8410
DGREY = 0x4208
DDGREY = 0x2104
STAR_TINTS = (0x9EFF, 0xFFB5, 0xFE79)


class Sky:
    def __init__(self, player, fx, fy, view):
        self.fx = fx
        self.fy = fy
        self.vx0, self.vy0, self.vx1, self.vy1, self.cx, self.cy = view
        # half the view's opening angle, in degrees
        self.ah = int(atan((self.vx1 - self.vx0) / 2 / fx) * 57.3)
        self.av = int(atan((self.vy1 - self.vy0) / 2 / fy) * 57.3)
        # --- stars: unit directions x 16384, colour, state (0 in view,
        # 1 lost, 2.. placed beyond the edge for that many turns)
        self.sd = array('h', [0] * (NSTAR * 3))
        self.sc = array('H', [0] * NSTAR)
        self.soff = bytearray(NSTAR)
        m = player.m
        for i in range(NSTAR):
            self._star_on_screen(i, m)
            k = randint(0, 99)
            if k < 52:
                c = DGREY
            elif k < 82:
                c = GREY
            elif k < 95:
                c = LGREY
            else:
                c = STAR_TINTS[k % 3]
            self.sc[i] = c
        # --- dust: positions in world units x 256, like the ships
        self.dp = array('i', [0] * (NDUST * 3))
        self.doff = bytearray(NDUST)
        for i in range(NDUST):
            self._place_dust(i, player)

    # --- set-up -----------------------------------------------------------
    def _star_on_screen(self, i, m):
        """A random direction inside the view of matrix m."""
        sx = randint(self.vx0, self.vx1 - 1) - self.cx
        sy = self.cy - randint(self.vy0, self.vy1 - 1)
        a = (sx << 14) // self.fx
        b = (sy << 14) // self.fy
        x = (a * m[0] + b * m[3]) // 16384 + m[6]
        y = (a * m[1] + b * m[4]) // 16384 + m[7]
        z = (a * m[2] + b * m[5]) // 16384 + m[8]
        self._set_star(i, x, y, z)

    def _set_star(self, i, x, y, z):
        n = M.mag(x, y, z)
        if n == 0:
            n = 1
        j = i * 3
        self.sd[j] = x * 16383 // n
        self.sd[j + 1] = y * 16383 // n
        self.sd[j + 2] = z * 16383 // n
        self.soff[i] = 0

    def _place_dust(self, i, p):
        """start_dust: ahead of the ship, spread by the forward speed."""
        vx, vy, vz = M.to_frame(p.m, p.vx >> 8, p.vy >> 8, p.vz >> 8)
        vx *= 10
        vy *= 10
        vz *= 10
        r = p.radius
        if vz >= 0:
            dist = (randint(0, vz) + r) * 2 + randint(0, 350)
            half = dist >> 1
            side = vx + randint(-half, half)
            up = vy + randint(-half, half)
        else:
            dist = randint(0, 40) + r
            half = dist >> 1
            side = vx + 2 * randint(-half, half)
            up = vy + 2 * randint(-half, half)
        m = p.m
        j = i * 3
        dp = self.dp
        dp[j] = p.x + ((m[6] * dist + m[0] * side + m[3] * up) >> 6)
        dp[j + 1] = p.y + ((m[7] * dist + m[1] * side + m[4] * up) >> 6)
        dp[j + 2] = p.z + ((m[8] * dist + m[2] * side + m[5] * up) >> 6)
        self.doff[i] = 0

    # --- once per game turn ---------------------------------------------
    def turn(self, p):
        # stars that left the view come back where the view is going
        if p.rp or p.ry:
            m = p.m
            tmp = [0] * 9
            soff = self.soff
            ah = self.ah
            av = self.av
            ary = abs(p.ry)
            arp = abs(p.rp)
            for i in range(NSTAR):
                o = soff[i]
                if o == 0:
                    continue
                if o >= 2:
                    # placed beyond the edge, waiting to come into view;
                    # given up after a dozen turns
                    soff[i] = o + 1
                    if o < 12:
                        continue
                for k in range(9):
                    tmp[k] = m[k]
                # the axis to enter from, weighted by how fast each turns
                if arp and randint(1, arp + ary) <= arp:
                    pi = av + randint(1, arp)
                    if p.rp < 0:
                        pi = -pi
                    ya = randint(-ah, ah)
                else:
                    ya = ah + randint(1, ary)
                    if p.ry < 0:
                        ya = -ya
                    pi = randint(-av, av)
                M.pitch(tmp, pi)
                M.yaw(tmp, ya)
                self._set_star(i, tmp[6], tmp[7], tmp[8])
                soff[i] = 2
        # dust that is out of reach is set up ahead again
        dp = self.dp
        m = p.m
        fx = self.fx
        fy = self.fy
        hw = (self.vx1 - self.vx0) // 2 + 8     # half the view + a margin
        hh = (self.vy1 - self.vy0) // 2 + 8
        for i in range(NDUST):
            j = i * 3
            dx = (dp[j] - p.x) >> 8
            dy = (dp[j + 1] - p.y) >> 8
            dz = (dp[j + 2] - p.z) >> 8
            if -DUST_FAR < dx < DUST_FAR and -DUST_FAR < dy < DUST_FAR and \
                    -DUST_FAR < dz < DUST_FAR:
                lx, ly, lz = M.to_frame(m, dx, dy, dz)
                gone = lz < p.radius or lz > DUST_FAR or \
                    abs(lx) * fx > lz * hw or abs(ly) * fy > lz * hh
            else:
                gone = True
            if gone and randint(0, 7) < 2:
                self._place_dust(i, p)

    # --- every picture ----------------------------------------------------
    def draw(self, fb, display, cam, ex, ey, ez, p, back):
        """back: the stars; else the dust."""
        if back:
            self._stars(display, cam)
        else:
            self._dust(display, cam, ex, ey, ez, p)

    @micropython.native
    def _stars(self, display, m):
        sd = self.sd
        sc = self.sc
        soff = self.soff
        fx = self.fx; fy = self.fy
        cx = self.cx; cy = self.cy
        x0 = self.vx0; x1 = self.vx1; y0 = self.vy0; y1 = self.vy1
        px = display.setPixel
        m0 = m[0]; m1 = m[1]; m2 = m[2]
        m3 = m[3]; m4 = m[4]; m5 = m[5]
        m6 = m[6]; m7 = m[7]; m8 = m[8]
        for i in range(NSTAR):
            j = i * 3
            x = sd[j]; y = sd[j + 1]; z = sd[j + 2]
            vz = (x * m6 + y * m7 + z * m8) >> 14
            if vz < 1500:
                if soff[i] < 2:
                    soff[i] = 1
                continue
            sx = cx + fx * ((x * m0 + y * m1 + z * m2) >> 14) // vz
            sy = cy - fy * ((x * m3 + y * m4 + z * m5) >> 14) // vz
            if x0 <= sx < x1 and y0 <= sy < y1:
                soff[i] = 0
                c = sc[i]
                px(sx, sy, c)
                if c != DGREY and c != GREY and c != LGREY:
                    # a tinted bright star: a faint cross around it
                    if sx > x0:
                        px(sx - 1, sy, DDGREY)
                    if sx < x1 - 1:
                        px(sx + 1, sy, DDGREY)
                    if sy > y0:
                        px(sx, sy - 1, DDGREY)
                    if sy < y1 - 1:
                        px(sx, sy + 1, DDGREY)
            elif soff[i] < 2:
                soff[i] = 1

    @micropython.native
    def _dust(self, display, m, ex, ey, ez, p):
        dp = self.dp
        fx = self.fx; fy = self.fy
        cx = self.cx; cy = self.cy
        x0 = self.vx0; x1 = self.vx1; y0 = self.vy0; y1 = self.vy1
        # half a turn of the ship's motion, in the camera's frame: where
        # each speck was relative to the eye a moment ago
        hx, hy, hz = M.to_frame(m, p.vx >> 9, p.vy >> 9, p.vz >> 9)
        line = display.drawLine
        fill = display.drawFilledRectangle
        for i in range(NDUST):
            j = i * 3
            dx = (dp[j] - ex) >> 8
            dy = (dp[j + 1] - ey) >> 8
            dz = (dp[j + 2] - ez) >> 8
            if dx > DUST_FAR or dx < -DUST_FAR or dy > DUST_FAR or \
                    dy < -DUST_FAR or dz > DUST_FAR or dz < -DUST_FAR:
                continue
            lx, ly, lz = M.to_frame(m, dx, dy, dz)
            if lz < 12:
                continue
            sx = cx + fx * lx // lz
            sy = cy - fy * ly // lz
            if sx < x0 or sx >= x1 or sy < y0 or sy >= y1:
                continue
            if lz < 180:
                col = LGREY
            elif lz < 520:
                col = GREY
            else:
                col = DGREY
            tz = lz + hz
            if tz > 12:
                tx = cx + fx * (lx + hx) // tz
                ty = cy - fy * (ly + hy) // tz
                if tx != sx or ty != sy:
                    line(tx, ty, sx, sy, DGREY if col != DGREY else DDGREY)
            if lz < 110:
                fill(sx, sy, 2, 2, col)
            else:
                display.setPixel(sx, sy, col)
