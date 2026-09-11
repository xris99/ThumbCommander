# bench_storage.py - storage-layout benchmark for the Stars/Astroids hot loops.
#
# ANSWERS: on the real firmware, is array('l') field access faster than
#   (a) the as-is code: per-field array subscripts in the loop
#   (b) the audit's rec: bind every field to a local once per entity,
#       do the math on locals, write back once at the end
#   (c) objects in the array that hold the fields as plain attributes
#       (direct s.x access, no getters/setters) - tested with a
#       dict-based class (c1) and a __slots__ class (c2)
#
# RUN: open this file in Thonny, connect to the device (Thumby or
# ThumbyColor), press F5. Set PLATFORM below to match. Takes ~1-3 min.
# Nothing is written to the device. PASTE THE FULL OUTPUT BACK.
#
# HONESTY NOTES:
#  * Thonny executes this as BYTECODE. The deployed game compiles
#    Stars.run/_update_astroid to machine code (@micropython.native via
#    mpy-cross). The a/b/c RANKING transfers; absolute us/frame do not
#    (machine code will be faster for all of them).
#  * The fpmath helpers below are plain (bytecode) copies of the real
#    ones, so every scenario pays identical arithmetic cost.
#  * Display calls are no-op'd; values use the real per-platform ranges
#    from games/thumbcommander/constants.py.
#  * The small-int probe at the top tells you whether values in these
#    loops allocate on THIS build (the audit's GC-churn claim hinges
#    on that).

import sys
import gc
import time

try:
    from time import ticks_us, ticks_diff
except ImportError:      # CPython dev-machine sanity run only
    import time as _t
    def ticks_us():
        return int(_t.monotonic() * 1e6) & 0xFFFFFFFF
    def ticks_diff(a, b):
        return (a - b) & 0xFFFFFFFF

from array import array

try:
    array('O', [1])          # MicroPython has object arrays; CPython does not
except ValueError:          # local CPython sanity run only
    _real_array = array

    def array(typecode, init=None):
        if typecode == 'O':
            return list(init) if init is not None else []
        return _real_array(typecode, init)

# ---------- SET THIS TO MATCH THE DEVICE YOU ARE ON ----------
PLATFORM = 'thumbycolor'   # or 'thumby'
TIME_FRAMES = 300          # timed frames per scenario
CHURN_FRAMES = 150         # gc.collect() per frame frames per scenario

if PLATFORM == 'thumby':
    N_STARS = 20           # PC.STAR_COUNT
    SPACE_W = 2047         # PC.SPACE_WIDTH
    SPACE_H = 1400         # PC.SPACE_HEIGHT
    Z_DIST = 30            # PC.Z_DISTANCE
    STAR_BOUND = 200       # PC.SPACE_STARS
    R0, R1 = 72, 576       # respawn radius range: (WIDTH//4)*4 .. (WIDTH*2)*4
    CX, CY = 36, 20
else:
    N_STARS = 30
    SPACE_W = 2559
    SPACE_H = 2559
    Z_DIST = 50
    STAR_BOUND = 350
    R0, R1 = 128, 1024
    CX, CY = 64, 64

N_AST = 5
ZD16 = Z_DIST << 16
SB16 = STAR_BOUND << 16
SW16 = SPACE_W << 16
SH16 = SPACE_H << 16

# player state (typical mid-game values; only cost matters, not exact)
player_speed = 65536 + 10 * 1311
player_angle = array('l', [300, -200, 150])
PA2 = player_angle[2]

# ---------- device identity ----------
print('== bench_storage v2 ==')
print('platform-set: ' + PLATFORM)
print(sys.version)
try:
    print('uname:', str(sys.uname()))
except Exception:
    pass
try:
    from machine import freq
    print('machine.freq():', list(freq()))
except Exception:
    pass
try:
    gc.mem_alloc()
    HAVE_MEMAPI = True
    print('ram free/alloc: %d / %d bytes' % (gc.mem_free(), gc.mem_alloc()))
except Exception:
    HAVE_MEMAPI = False
    print('NOTE: gc.mem_free/alloc not available here - memory columns skipped')
print('stars=%d  asteroids=%d  frames: time=%d churn=%d' %
      (N_STARS, N_AST, TIME_FRAMES, CHURN_FRAMES))


def gc_freed():
    # this firmware's gc.collect() returns None, not a count
    r = gc.collect()
    return 0 if r is None else r


# ---------- small-int range probe ----------
# The whole GC-churn question depends on this: if every value in the
# loops fits the small-int encoding, array('l') reads/writes and the
# arithmetic allocate NOTHING and the audit's churn theory cannot hold.
# NOTE: the allocation must be measured at CREATION time - storing an
# already-built value never allocates, so probing pre-built values
# proves nothing (that was the v1 bug).
def create_bytes(make):
    gc.collect()
    b = gc.mem_alloc()
    v = make()
    d = gc.mem_alloc() - b
    return d


if HAVE_MEMAPI:
    print('--- small-int probe: bytes allocated when CREATING each value ---')
    print('  (0 B = fits the small-int encoding, no heap; >0 = MPZ bignum)')
    s29, s30, s40 = 29, 30, 40
    for nm, mk in [
        ('2^29-1',   lambda: (1 << s29) - 1),
        ('2^29',     lambda: 1 << s29),
        ('2^30-1',   lambda: (1 << s30) - 1),
        ('2^30',     lambda: 1 << s30),
        ('-(2^30)',  lambda: -(1 << s30)),
        ('2^40',     lambda: 1 << s40),
    ]:
        print('  %9s : %d B' % (nm, create_bytes(mk)))
    w = SPACE_W
    print('  %d<<19  : %d B  <- (x<<3) fed to project() for an extreme x' %
          (w, create_bytes(lambda: w << 19)))
    print('  => if 2^30 allocates, the small-int range is +/-2^30 and every')
    print('     game value above (max ~2559<<16 <<3) crosses into bignum land')

# ---------- fixed-point math: plain copies of thumby_engine/util/fpmath.py ----------
# 16-entry quarter-wave sine table (0..90 deg), mirrored in code exactly
# like the real 1024-entry table. Accuracy is irrelevant to the bench -
# only the access/op cost matters.
_Q = (0, 6850, 13625, 20251, 26661, 32768, 38515, 43850,
      48702, 53019, 56755, 59870, 62327, 64102, 65176, 65536)  # sin * 65536
sintab = array('l', _Q)


def fpsin(a):
    a &= 63
    ta = a & 15
    if (a & 32) >= 16:
        ta = 15 - ta
    v = sintab[ta]
    if a >= 32:
        return 0 - v
    return v


def fpcos(a):
    return fpsin(a + 16)


def int2fp(v):
    return v << 16


def fp2int(v):
    return v >> 16


def fpmul(a, b):
    return (a >> 8) * (b >> 8)


def fpdiv(a, b):
    return a if (b >> 3) == 0 else ((a << 3) // (b >> 3)) << 10


def project(xy, z, center_xy, sprite_wh=0):
    a = fpdiv(xy, abs(z))
    b = a >> 16
    c = sprite_wh >> 1
    return b + center_xy - c


def rotate_z_x(x, y, angle):
    return fpmul(x, fpcos(angle)) - fpmul(y, fpsin(angle))


def rotate_z_y(x, y, angle):
    return fpmul(x, fpsin(angle)) + fpmul(y, fpcos(angle))


# ---------- deterministic data (same start state for every scenario) ----------
_rs = 987654321


def rnd(lo, hi):
    global _rs
    _rs = (_rs * 1103515245 + 12345) & 0x7FFFFFFF
    return lo + (_rs % (hi - lo + 1))


def build_vals():
    global _rs
    _rs = 987654321
    stars = []
    for i in range(N_STARS):
        if i % 5 == 0:     # ~20% moving stars, like the real stable=80
            stars.append([rnd(-STAR_BOUND, STAR_BOUND) << 16,
                          rnd(-STAR_BOUND, STAR_BOUND) << 16,
                          rnd(5, Z_DIST) << 16,
                          rnd(0, 3),
                          rnd(42598, 62258)])
        else:
            stars.append([rnd(-STAR_BOUND, STAR_BOUND) << 16,
                          rnd(-STAR_BOUND, STAR_BOUND) << 16,
                          7 << 16,
                          rnd(0, 3),
                          0])
    asts = []
    for i in range(N_AST):
        asts.append([rnd(-SPACE_W, SPACE_W) << 16,
                     rnd(-SPACE_H, SPACE_H) << 16,
                     rnd(20, 70) << 16,
                     rnd(-655360, 655360),
                     rnd(-655360, 655360),
                     rnd(6554, 13107),
                     rnd(0, 1),
                     rnd(2, 4),
                     0])
    return stars, asts


# ---------- scenario (c) object classes ----------
def make_class(name, names, slots):
    def __init__(self, v):
        for i in range(len(names)):
            setattr(self, names[i], v[i])
    ns = {'__init__': __init__}
    if slots:
        ns['__slots__'] = tuple(names)
    return type(name, (object,), ns)


STAR_NAMES = ('x', 'y', 'z', 'color', 'speed')
AST_NAMES = ('x', 'y', 'z', 'vx', 'vy', 'vz', 'shape', 'rot', 'step')
StarDict = make_class('StarDict', STAR_NAMES, False)
StarSlots = make_class('StarSlots', STAR_NAMES, True)
AstDict = make_class('AstDict', AST_NAMES, False)
AstSlots = make_class('AstSlots', AST_NAMES, True)

# =====================================================================
# STAR frame functions - mirror of MainGame Stars.run (display no-op'd)
# =====================================================================

def star_a(stars):
    # (a) as-is: per-field array subscripts, exactly like MainGame
    ps = player_speed
    pa = player_angle
    for s in stars:
        x = project(s[0], s[2], CX, 0)
        y = project(s[1], s[2], CY, 0)
        size = 1 if s[4] == 0 else fp2int(fpdiv(ZD16, fpmul(72090, s[2])))
        # display.drawFilledRectangle(x, y, size, size, s[3])
        if s[4] == 0:
            for c in range(2):
                s[c] += pa[c] // 2 + (ps - 65536)
                if (s[c] > SB16) or (s[c] < -SB16):
                    s[c] = -s[c]
        s[2] -= fpmul(s[4], ps)
        if PA2 != 0:
            new_x = rotate_z_x(s[0], s[1], PA2)
            s[1] = rotate_z_y(s[0], s[1], PA2)
            s[0] = new_x
        if s[2] < (1 << 16):
            a = rnd(0, 4096)
            radius = rnd(R0, R1) << 16
            s[0] = fpmul(radius, fpcos(a))
            s[1] = fpmul(radius, fpsin(a))
            s[2] = ZD16


def star_b(stars):
    # (b) audit rec: bind fields to locals, math on locals, write back once
    ps = player_speed
    pa0 = player_angle[0]
    pa1 = player_angle[1]
    for s in stars:
        x0 = s[0]
        y0 = s[1]
        z0 = s[2]
        spd = s[4]
        x = project(x0, z0, CX, 0)
        y = project(y0, z0, CY, 0)
        size = 1 if spd == 0 else fp2int(fpdiv(ZD16, fpmul(72090, z0)))
        if spd == 0:
            x0 += pa0 // 2 + (ps - 65536)
            if (x0 > SB16) or (x0 < -SB16):
                x0 = -x0
            y0 += pa1 // 2 + (ps - 65536)
            if (y0 > SB16) or (y0 < -SB16):
                y0 = -y0
        z0 -= fpmul(spd, ps)
        if PA2 != 0:
            nx = rotate_z_x(x0, y0, PA2)
            y0 = rotate_z_y(x0, y0, PA2)
            x0 = nx
        if z0 < (1 << 16):
            a = rnd(0, 4096)
            radius = rnd(R0, R1) << 16
            x0 = fpmul(radius, fpcos(a))
            y0 = fpmul(radius, fpsin(a))
            z0 = ZD16
        s[0] = x0
        s[1] = y0
        s[2] = z0


def star_c(stars):
    # (c) object with plain attributes, accessed directly, no locals
    ps = player_speed
    pa0 = player_angle[0]
    pa1 = player_angle[1]
    for s in stars:
        x = project(s.x, s.z, CX, 0)
        y = project(s.y, s.z, CY, 0)
        size = 1 if s.speed == 0 else fp2int(fpdiv(ZD16, fpmul(72090, s.z)))
        if s.speed == 0:
            s.x += pa0 // 2 + (ps - 65536)
            if (s.x > SB16) or (s.x < -SB16):
                s.x = -s.x
            s.y += pa1 // 2 + (ps - 65536)
            if (s.y > SB16) or (s.y < -SB16):
                s.y = -s.y
        s.z -= fpmul(s.speed, ps)
        if PA2 != 0:
            nx = rotate_z_x(s.x, s.y, PA2)
            s.y = rotate_z_y(s.x, s.y, PA2)
            s.x = nx
        if s.z < (1 << 16):
            a = rnd(0, 4096)
            radius = rnd(R0, R1) << 16
            s.x = fpmul(radius, fpcos(a))
            s.y = fpmul(radius, fpsin(a))
            s.z = ZD16

# =====================================================================
# ASTEROID frame functions - mirror of _update_astroid + the per-asteroid
# part of Astroids.run (getSprite/project/frame-step; sort and laser
# checks are out of scope for a storage bench)
# =====================================================================

def ast_a(asts):
    ps = player_speed
    pa = player_angle
    for a in asts:
        for c in range(2):
            if (a[c] > SW16) or (a[c] < -SW16):
                a[c + 3] = -a[c + 3]
            a[c] += a[c + 3]
            a[c] += pa[c] + (ps - 65536)
        a[2] -= fpmul(a[5], ps)
        if PA2 != 0:
            nx = rotate_z_x(a[0], a[1], PA2)
            a[1] = rotate_z_y(a[0], a[1], PA2)
            a[0] = nx
        scale = fpdiv(fpmul((71 << 16) - abs(a[2]), 113377), 60 << 16)
        x = project(a[0], a[2], CX, 0)
        y = project(a[1], a[2], CY, 0)
        n = a[8] // a[7]
        if n > 12:
            n = 0
            a[8] = 0
        else:
            a[8] += 1
        if a[6] == 0 and n == 6:      # explosion done: respawn in place
            a[0] = rnd(-SPACE_W, SPACE_W) << 16
            a[1] = rnd(-SPACE_H, SPACE_H) << 16
            a[2] = rnd(20, 70) << 16
            a[3] = rnd(-655360, 655360)
            a[4] = rnd(-655360, 655360)
            a[5] = rnd(6554, 13107)
            a[6] = rnd(0, 1)
            a[8] = 0


def ast_b(asts):
    ps = player_speed
    pa0 = player_angle[0]
    pa1 = player_angle[1]
    for a in asts:
        x0 = a[0]
        y0 = a[1]
        z0 = a[2]
        vx = a[3]
        vy = a[4]
        vz = a[5]
        shape = a[6]
        rot = a[7]
        step = a[8]
        if (x0 > SW16) or (x0 < -SW16):
            vx = -vx
        x0 += vx
        x0 += pa0 + (ps - 65536)
        if (y0 > SW16) or (y0 < -SW16):
            vy = -vy
        y0 += vy
        y0 += pa1 + (ps - 65536)
        z0 -= fpmul(vz, ps)
        if PA2 != 0:
            nx = rotate_z_x(x0, y0, PA2)
            y0 = rotate_z_y(x0, y0, PA2)
            x0 = nx
        scale = fpdiv(fpmul((71 << 16) - abs(z0), 113377), 60 << 16)
        x = project(x0, z0, CX, 0)
        y = project(y0, z0, CY, 0)
        n = step // rot
        if n > 12:
            n = 0
            step = 0
        else:
            step += 1
        if shape == 0 and n == 6:
            x0 = rnd(-SPACE_W, SPACE_W) << 16
            y0 = rnd(-SPACE_H, SPACE_H) << 16
            z0 = rnd(20, 70) << 16
            vx = rnd(-655360, 655360)
            vy = rnd(-655360, 655360)
            vz = rnd(6554, 13107)
            shape = rnd(0, 1)
            step = 0
        a[0] = x0
        a[1] = y0
        a[2] = z0
        a[3] = vx
        a[4] = vy
        a[5] = vz
        a[6] = shape
        a[8] = step


def ast_c(asts):
    ps = player_speed
    pa0 = player_angle[0]
    pa1 = player_angle[1]
    for a in asts:
        if (a.x > SW16) or (a.x < -SW16):
            a.vx = -a.vx
        a.x += a.vx
        a.x += pa0 + (ps - 65536)
        if (a.y > SW16) or (a.y < -SW16):
            a.vy = -a.vy
        a.y += a.vy
        a.y += pa1 + (ps - 65536)
        a.z -= fpmul(a.vz, ps)
        if PA2 != 0:
            nx = rotate_z_x(a.x, a.y, PA2)
            a.y = rotate_z_y(a.x, a.y, PA2)
            a.x = nx
        scale = fpdiv(fpmul((71 << 16) - abs(a.z), 113377), 60 << 16)
        x = project(a.x, a.z, CX, 0)
        y = project(a.y, a.z, CY, 0)
        n = a.step // a.rot
        if n > 12:
            n = 0
            a.step = 0
        else:
            a.step += 1
        if a.shape == 0 and n == 6:
            a.x = rnd(-SPACE_W, SPACE_W) << 16
            a.y = rnd(-SPACE_H, SPACE_H) << 16
            a.z = rnd(20, 70) << 16
            a.vx = rnd(-655360, 655360)
            a.vy = rnd(-655360, 655360)
            a.vz = rnd(6554, 13107)
            a.shape = rnd(0, 1)
            a.step = 0

# =====================================================================
# measurement
# =====================================================================

_hold = []


def time_pass(fn, data):
    global _rs
    _rs = 987654321             # deterministic respawn sequence per pass
    for _ in range(50):          # warmup (also fills any caches)
        fn(data)
    t0 = ticks_us()
    worst = 0
    for _ in range(TIME_FRAMES):
        tf = ticks_us()
        fn(data)
        dt = ticks_diff(ticks_us(), tf)
        if dt > worst:
            worst = dt
    tot = ticks_diff(ticks_us(), t0)
    return tot, worst


def churn_pass(fn, data):
    # freed objects per frame: a proxy for allocation churn.
    # ~0 means the loop allocates nothing (small-int world).
    # Returns None if this build's gc.collect() reports no count.
    global _rs
    _rs = 987654321
    if gc.collect() is None:
        return None
    freed = 0
    for _ in range(CHURN_FRAMES):
        fn(data)
        freed += gc_freed()
    return freed


def mem_entity(vals, factory, empty):
    # bytes per entity, with the container's own slots subtracted out
    if not HAVE_MEMAPI:
        return -1
    _hold.clear()
    _hold.append(empty)
    gc.collect()
    b = gc.mem_alloc()
    _hold.clear()
    _hold.append([factory(v) for v in vals])
    m = gc.mem_alloc()
    return (m - b) // len(vals)


def run_scenario(label, fn, vals, factory, empty):
    data = [factory(v) for v in vals]
    tot, worst = time_pass(fn, data)
    us = tot // TIME_FRAMES          # tot is in us -> us/frame
    # print the timing result first so a later failure can't lose it
    try:
        data2 = [factory(v) for v in vals]
        freed = churn_pass(fn, data2)
        _hold.clear()
        _hold.append(data2)      # keep alive while we print, freed next scenario
        churn_s = 'n/a' if freed is None else '%.1f' % (freed / float(CHURN_FRAMES))
    except Exception:
        churn_s = 'ERR'
    try:
        be = mem_entity(vals, factory, empty) if HAVE_MEMAPI else -1
    except Exception:
        be = -1
    print('  %-10s %7d us/f  max %6d us  churn %8s obj/f  mem %4d B/entity' %
          (label, us, worst, churn_s, be))


print('')
print('--- stars: %d entities x 5 fields ---' % N_STARS)
sv, av = build_vals()
run_scenario('a:array', star_a, sv, lambda v: array('l', v), array('O', [None] * N_STARS))
run_scenario('b:locals', star_b, sv, lambda v: array('l', v), array('O', [None] * N_STARS))
run_scenario('c1:dict', star_c, sv, StarDict, [None] * N_STARS)
run_scenario('c2:slots', star_c, sv, StarSlots, [None] * N_STARS)

print('--- asteroids: %d entities x 9 fields ---' % N_AST)
run_scenario('a:array', ast_a, av, lambda v: array('l', v), [None] * N_AST)
run_scenario('b:locals', ast_b, av, lambda v: array('l', v), [None] * N_AST)
run_scenario('c1:dict', ast_c, av, AstDict, [None] * N_AST)
run_scenario('c2:slots', ast_c, av, AstSlots, [None] * N_AST)

print('')
print('== done. Paste this whole output back. ==')
