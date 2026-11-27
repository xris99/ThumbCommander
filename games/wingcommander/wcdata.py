# wcdata.py - loaders for the converted Wing Commander assets.
#
# Every file read here is written by tool/wc1_convert.py from the
# player's own copy of the game; see that tool for the layouts. Records
# keep the original on-disk formats (wc1-re src/cmpgn.c, wcdata.h), so
# the device code reads the same fields the original game does.

from struct import unpack_from
from array import array
import os
import wcgfx

A = 'assets/'


def exists(name):
    """Stat, never open: open allocates the filesystem's own file
    buffer - 1,148 bytes on ThumbyColor - and a fragmented heap has
    refused that ask in a tight phase (device log, docs/12 12.1).
    A stat costs a small tuple, nothing wide."""
    try:
        os.stat(A + name)
        return True
    except OSError:
        return False


def load(name):
    f = open(A + name, 'rb')
    d = f.read()
    f.close()
    return d


def cstr(raw, start=0, limit=-1):
    """NUL terminated bytes out of a record (original text stays bytes:
    the fonts are indexed by character code)."""
    end = len(raw) if limit < 0 else min(len(raw), start + limit)
    i = start
    while i < end and raw[i] != 0:
        i += 1
    return bytes(raw[start:i])


# --- object types ------------------------------------------------------------
# field order written by the converter
(T_CLASS, T_RADIUS, T_MASS, T_SCALE, T_ANIM_DELAY, T_LIFETIME, T_DAMAGE,
 T_EXPLOSION, T_MAX_VEL, T_CRUISE, T_ACCEL, T_PITCH, T_YAW, T_ROLL, T_AB,
 T_SHIELD_F, T_SHIELD_A, T_ARMOR_F, T_ARMOR_R, T_ARMOR_L,
 T_ARMOR_RT) = range(21)


class Types:
    def __init__(self):
        d = load('types.wc')
        n = self.count = d[0]
        nf = d[1]
        self.max_weapons = d[2]
        name_size = d[3]
        pos = 4
        self.f = []
        for _ in range(nf):
            self.f.append(array('i', unpack_from('<%di' % n, d, pos)))
            pos += n * 4
        wsize = 1 + self.max_weapons * 3
        self._weapons = d[pos:pos + n * wsize]
        self._wsize = wsize
        pos += n * wsize
        self.names = []
        for i in range(n):
            self.names.append(cstr(d, pos + i * name_size, name_size))
        pos += n * name_size
        self.child = array('h', unpack_from('<168h', d, pos))
        pos += 336
        self.dir_frame = bytes(d[pos:pos + 186])
        pos += 186
        self.dir_flip = bytes(d[pos:pos + 186])

    def get(self, field, typ):
        return self.f[field][typ]

    def weapons(self, typ):
        """Fresh loadout: list of [weapon type, hardpoint, disabled]."""
        w = self._weapons
        o = typ * self._wsize
        out = []
        for i in range(w[o]):
            dis = w[o + 3 + i * 3]
            out.append([w[o + 1 + i * 3], w[o + 2 + i * 3],
                        1 if dis else 0])
        return out


class Ai:
    """ai.wc: pilot AI and campaign tables kept inside WC.EXE."""

    def __init__(self):
        d = load('ai.wc')
        pos = 4
        self.defense = []
        for _ in range(5):
            n = d[pos]
            self.defense.append(bytes(d[pos + 1:pos + 1 + n]))
            pos += 1 + n
        self.rated = array('b', unpack_from('<1053b', d, pos)); pos += 1053
        self.kilrathi = array('b', unpack_from('<405b', d, pos)); pos += 405
        self.aggression = bytes(d[pos:pos + 24]); pos += 24
        self.recovery = bytes(d[pos:pos + 20]); pos += 20
        self.turn = bytes(d[pos:pos + 18]); pos += 18
        self.formation = array('h', unpack_from('<120h', d, pos)); pos += 240
        self.refire = bytes(d[pos:pos + 4]); pos += 4
        self.colours = bytes(d[pos:pos + 12]); pos += 12
        self.pilots = []
        for _ in range(9):
            self.pilots.append((cstr(d, pos, 14), cstr(d, pos + 14, 14),
                                d[pos + 28], d[pos + 29], d[pos + 30]))
            pos += 31
        self.ranks = []
        for _ in range(5):
            self.ranks.append(cstr(d, pos, 10)); pos += 10
        self.medals = []
        for _ in range(5):
            self.medals.append(cstr(d, pos, 24)); pos += 24
        self.player_damage = bytes(d[pos:pos + 50])


# --- sprites -----------------------------------------------------------------

class SpriteSet:
    """Frame table of one .wcs file. The file itself is only opened for
    the moment a frame is read (a cache miss), so a mission with many
    ship types holds no file handles open."""
    _uid = 0

    def __init__(self, name):
        self.name = A + name
        f = open(self.name, 'rb')
        head = f.read(8)
        self.n = head[4]
        self.res = head[5]
        self.largest = head[6] | (head[7] << 8)
        self.table = f.read(self.n * 8)
        f.close()
        SpriteSet._uid += 1
        self.uid = SpriteSet._uid

    def has(self, frame):
        return 0 <= frame < self.n and \
            unpack_from('<I', self.table, frame * 8)[0] != 0

    def read(self, off, view):
        f = open(self.name, 'rb')
        f.seek(off)
        f.readinto(view)
        f.close()


# Frame pools of a flight: (slots, bytes per slot), smallest first. The
# converter keeps every ship frame within the last size (MAX_SHIP_PIXELS
# in tool/wc1_convert.py) - change both together.
#   tiny   bolts, missiles, sparks, debris
#   small  fighters, explosions
#   big    capital ships
POOLS = ((10, 640), (7, 2112), (2, 3600))
MAX_FRAME = POOLS[-1][1]
CK_SIZE = 20 + 128 * 96             # one ck<N>.wc


class FrameCache:
    """Fixed pools of frame buffers (no allocation while flying).

    A slot holds the pixels of one (sprite set, frame); the least
    recently used slot of the smallest pool that fits is reused on a
    miss. Create it once, early, while the heap is still in one piece:
    these are the largest blocks the game ever asks for.
    """

    def __init__(self, pools=POOLS):
        self.buf = []
        self.lo = []                    # first slot of each pool
        self.size = []
        for count, size in pools:
            self.lo.append(len(self.buf))
            self.size.append(size)
            for _ in range(count):
                self.buf.append(bytearray(size))
        n = len(self.buf)
        self.lo.append(n)
        self.view = [memoryview(b) for b in self.buf]
        self.key = [-1] * n
        self.age = [0] * n
        self.w = bytearray(n)
        self.h = bytearray(n)
        self.hx = array('h', [0] * n)
        self.hy = array('h', [0] * n)
        self.res = bytearray(n)
        self.clock = 0

    def reset(self):
        """Forget every frame (a new flight numbers its sets afresh)."""
        for i in range(len(self.key)):
            self.key[i] = -1
            self.age[i] = 0
        self.clock = 0

    @micropython.native
    def get(self, sset, frame):
        """Slot index holding the frame, or -1 if it cannot be shown."""
        key = sset.uid * 256 + frame
        keys = self.key
        self.clock += 1
        n = len(keys)
        i = 0
        while i < n:
            if keys[i] == key:
                self.age[i] = self.clock
                return i
            i += 1
        if frame < 0 or frame >= sset.n:
            return -1
        off, w, h, hx, hy = unpack_from('<IBBbb', sset.table, frame * 8)
        size = w * h
        if off == 0 or size == 0:
            return -1
        sizes = self.size
        pool = 0
        while pool < len(sizes) and size > sizes[pool]:
            pool += 1
        if pool == len(sizes):
            return -1
        lo = self.lo[pool]
        hi = self.lo[pool + 1]
        best = lo
        i = lo
        while i < hi:
            if self.age[i] < self.age[best]:
                best = i
            i += 1
        sset.read(off, self.view[best][0:size])
        keys[best] = key
        self.age[best] = self.clock
        self.w[best] = w
        self.h[best] = h
        self.hx[best] = hx
        self.hy[best] = hy
        self.res[best] = sset.res
        return best


# --- text --------------------------------------------------------------------

class Font:
    def __init__(self, index):
        self.data = load('font%d.wc' % index)
        self.h = self.data[0]

    def width(self, text):
        d = self.data
        w = 0
        for ch in text:
            w += d[2 + ch]
        return w

    def draw(self, fb, text, x, y, col):
        d = self.data
        g = wcgfx.glyph
        for ch in text:
            x += g(fb, d, ch, x, y, col)
        return x

    def centre(self, fb, text, y, col):
        self.draw(fb, text, (128 - self.width(text)) // 2, y, col)

    def wrap(self, text, width):
        """Word wrap bytes into a list of lines."""
        d = self.data
        lines = []
        line = b''
        lw = 0
        space = d[2 + 32]
        for word in text.split(b' '):
            ww = 0
            for ch in word:
                ww += d[2 + ch]
            if line and lw + space + ww > width:
                lines.append(line)
                line = word
                lw = ww
            elif line:
                line = line + b' ' + word
                lw += space + ww
            else:
                line = word
                lw = ww
        if line:
            lines.append(line)
        return lines


# --- missions ----------------------------------------------------------------
NAV_SIZE = 77
SHIP_SIZE = 42
OBJECTIVE_SIZE = 64


class Mission:
    """One MODULE mission record (LoadMissionData)."""

    def __init__(self, campaign, series, mission):
        f = open(A + 'mod%d.wc' % campaign, 'rb')
        head = f.read(8)
        count, stride = unpack_from('<HH', head, 4)
        index = mission + series * 4
        f.seek(8 + index * stride)
        rec = f.read(stride)
        f.seek(8 + count * stride + series * 40)
        self.series_name = cstr(f.read(40))
        f.close()
        h = unpack_from('<12h', rec, 0)
        self.entry_nav = h[0]
        self.home_ship = h[1]
        self.player_ship = h[2]
        self.initial = h[3:11]
        self.valid = self.player_ship >= 0
        self._nav = rec[24:24 + 16 * NAV_SIZE]
        base = 24 + 16 * NAV_SIZE
        self.objectives = []          # [type, index, text, flags]
        for i in range(16):
            o = base + i * OBJECTIVE_SIZE
            typ, idx = unpack_from('<hh', rec, o)
            if typ == -1:
                break
            self.objectives.append([typ, idx, cstr(rec, o + 4, 60), 0])
        base += 16 * OBJECTIVE_SIZE
        self._ships = rec[base:base + 32 * SHIP_SIZE]
        # mutable per-flight state (the game patches its in-memory copy)
        self.nav_type = bytearray(16)
        for i in range(16):
            self.nav_type[i] = self._nav[i * NAV_SIZE + 30]
        self.ship_state = bytearray(32)
        self.ship_nav = bytearray(32)
        for i in range(32):
            o = i * SHIP_SIZE
            self.ship_state[i] = self._ships[o + 36] & 0xFF
            self.ship_nav[i] = self._ships[o + 8] & 0xFF

    # nav points ----------------------------------------------------------
    def nav_name(self, i):
        return cstr(self._nav, i * NAV_SIZE, 30)

    def nav_pos(self, i):
        return unpack_from('<3i', self._nav, i * NAV_SIZE + 31)

    def nav_radius(self, i):
        return unpack_from('<H', self._nav, i * NAV_SIZE + 43)[0]

    def nav_triggers(self, i):
        return unpack_from('<8b', self._nav, i * NAV_SIZE + 45)

    def nav_ships(self, i):
        return unpack_from('<10h', self._nav, i * NAV_SIZE + 57)

    # ships -----------------------------------------------------------------
    def ship(self, i):
        """(type, side, leader, field5, mission type, nav, x, y, z, pitch,
        yaw, roll, formation spot, speed, rating, pilot, f2c, f2e, state,
        leader index, formation, target)"""
        return unpack_from('<hhbbhb3i3hbhhhhhbbbb', self._ships,
                           i * SHIP_SIZE)

    def ship_type(self, i):
        return unpack_from('<h', self._ships, i * SHIP_SIZE)[0]


class Campaign:
    """CAMP.00x section 1: the series tree (UpdateSeries)."""

    def __init__(self, campaign):
        d = load('camp%d.wc' % campaign)
        n = d[4]
        sizes = unpack_from('<%dH' % n, d, 5)
        pos = 5 + n * 2 + sizes[0]
        self.info = bytes(d[pos:pos + sizes[1]])

    def series(self, s):
        """(debrief pilot, missions, required score, sequence, win series,
        win ship, lose series, lose ship)"""
        b = (s - 1) * 0x5A
        return unpack_from('<hb', self.info, b) + \
            unpack_from('<h', self.info, b + 3) + \
            unpack_from('<5b', self.info, b + 5)

    def mission(self, s, m):
        """(medal, medal score) + 16 objective scores"""
        b = (s - 1) * 0x5A + 10 + m * 20
        return unpack_from('<hh16b', self.info, b)


def briefing_packet(campaign, series, mission):
    """The BRIEFING.00x packet of one mission (b'' if absent)."""
    f = open(A + 'brf%d.wc' % campaign, 'rb')
    n = unpack_from('<I', f.read(8), 4)[0]
    index = mission + series * 4
    if index >= n:
        f.close()
        return b''
    f.seek(8 + index * 8)
    off, size = unpack_from('<II', f.read(8), 0)
    data = b''
    if off and size:
        f.seek(off)
        data = f.read(size)
    f.close()
    return data


PIC_SIZE = 128 * 62              # one head base, one backdrop frame


# --- talking heads -----------------------------------------------------------

class Head:
    """head<NN>.wc ('WCH1'): one conversation face (docs/05 5.6). The
    base picture is w*h palette indices, 0 = transparent so the
    backdrop shows around the head; the ten mouth and ten eye patches
    are rectangles of the base with one expression composited in -
    they were cut from the same scaled picture, so they line up
    exactly. A zero patch draws nothing (TALKING1.VGA faces have only
    nine eye frames).

    Source: CloseTalk composes head frame 0 at (0, 0), the eye patch
    for faceFrame + 11 at the face origin and the mouth patch for
    mouthFrame + 1 at the mouth origin (wc1-re src/cmpgn.c)."""

    def __init__(self, face):
        d = load('head%02d.wc' % face)
        self.w = d[6]
        self.h = d[7]
        self.mouth_rect = unpack_from('<4B', d, 8)
        self.eye_rect = unpack_from('<4B', d, 12)
        n = self.w * self.h
        self.base = memoryview(d)[16:16 + n]
        pos = 16 + n
        mw = self.mouth_rect[2] * self.mouth_rect[3]
        self.mouth = [memoryview(d)[pos + i * mw:pos + (i + 1) * mw]
                      for i in range(10)]
        pos += 10 * mw
        ew = self.eye_rect[2] * self.eye_rect[3]
        self.eye = [memoryview(d)[pos + i * ew:pos + (i + 1) * ew]
                    for i in range(10)]


# --- conversation backdrops --------------------------------------------------

class Backdrops:
    """bdrop.wc ('WBD1'): 128 x 62 indexed conversation backdrops.
    Entries are keyed by scene type * 16 + conversation character -
    the character to backdrop switch in LoadFace (wc1-re
    src/cmpgn.c:215-257, tables.BACKDROP_BY_CHARACTER). kind 2 entries
    have a star field baked in (flags bit 1). The bodies are
    contiguous 7,936 byte frames; one seek reads the frame that is
    being shown, so all fourteen never sit in RAM at once."""

    SIZE = PIC_SIZE

    def __init__(self):
        f = open(A + 'bdrop.wc', 'rb')
        if f.read(4) != b'WBD1':
            raise ValueError('bdrop.wc is not WBD1')
        self.n = f.read(1)[0]
        self.table = f.read(self.n * 2)
        self.base = 5 + self.n * 2
        f.close()

    def index(self, kind, char):
        """Table entry for this scene type and character, -1 for none."""
        k = kind * 16 + char
        t = self.table
        for i in range(self.n):
            if t[2 * i] == k:
                return i
        return -1

    def stars(self, i):
        return self.table[2 * i + 1] & 1

    def read(self, i, view):
        f = open(A + 'bdrop.wc', 'rb')
        f.seek(self.base + i * self.SIZE)
        f.readinto(view)
        f.close()


# --- cutscenes ---------------------------------------------------------------

class Scene:
    """mid<NN>.wc ('WCG1'): one "Meanwhile" cutscene with its won and
    lost variant (docs/06 6.1). The index - primary shape table and
    the two variant tables - stays in RAM (a few hundred bytes); the
    blocks of a variant (object records, instructions, shape table,
    shape pixels, scene packet) are read once when an animation
    starts, and single shape frames are read into a scratch buffer."""

    OBJ_SIZE = 16                # '<BBiiHhh': layer, frame (the draw
                                 # site uses it as flip bits), x and y
                                 # in original-pixel i32 - scaled to
                                 # the device's 8.7 units only at the
                                 # draw site (scene.py _x8/_y8), so
                                 # goal tests stay exact integers,
                                 # scale, first instruction index,
                                 # rotation in degrees

    def __init__(self, scene):
        self.name = 'mid%02d.wc' % scene
        f = open(A + self.name, 'rb')
        head = f.read(12)
        if head[:4] != b'WCG1':
            raise ValueError(self.name + ' is not WCG1')
        self.scene = head[4]
        self.nvar = head[5]
        self.npri = unpack_from('<H', head, 6)[0]
        self.pri_off = unpack_from('<I', head, 8)[0]
        self.pri_tbl = bytes(f.read(self.npri * 8))
        self.v = []
        for _ in range(self.nvar):
            d = f.read(32)
            self.v.append((unpack_from('<6H', d, 0),
                           unpack_from('<5I', d, 12)))
        f.close()

    def variant(self, v):
        """((per, nanim, nobjs, ninstrs, nsec, pktlen),
        (obj_off, ins_off, sectbl_off, secpix_off, pkt_off))."""
        return self.v[v]

    def block(self, off, n):
        f = open(A + self.name, 'rb')
        f.seek(off)
        d = f.read(n)
        f.close()
        return d

    def objects(self, v):
        cnt, off = self.v[v]
        return self.block(off[0], cnt[2] * self.OBJ_SIZE) if cnt[2] else b''

    def instructions(self, v):
        cnt, off = self.v[v]
        return self.block(off[1], cnt[3] * 4) if cnt[3] else b''

    def sec_table(self, v):
        cnt, off = self.v[v]
        return self.block(off[2], cnt[4] * 8) if cnt[4] else b''

    def packet(self, v):
        cnt, off = self.v[v]
        return self.block(off[4], cnt[5]) if cnt[5] else b''

    def frame(self, tbl, index, view, base):
        """One '<IBBbb' entry of a shape table (pixel offsets relative
        to base): (w, h, hot_x, hot_y), or None for an empty slot.
        The indices land at the front of `view`."""
        off, w, h, hx, hy = unpack_from('<IBBbb', tbl, index * 8)
        n = w * h
        if off == 0 or n == 0:
            return None
        f = open(A + self.name, 'rb')
        f.seek(base + off)
        f.readinto(view[0:n])
        f.close()
        return w, h, hx, hy

    def pri_frame(self, index, view):
        return self.frame(self.pri_tbl, index, view, self.pri_off)

    def sec_frame(self, v, index, tbl, view):
        return self.frame(tbl, index, view, self.v[v][1][3])
