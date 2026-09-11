# bench_div.py - division-cost benchmark with the game's actual divisors.
#
# ANSWERS:
#   1. What does `//` (and `%`) actually cost on THIS device?
#      (expected: M0+ = software divide loop; M4 = one sdiv instruction)
#   2. Is a bit-shift a valid replacement? (only exact for powers of two)
#   3. What does magic-number multiply+shift ((x*m)>>k) cost here -
#      on 32-bit MicroPython the big product becomes a heap MPZ bignum,
#      which plain C never has to worry about
#   4. Whole-expression cost of the fpdiv/fpdiv_a shapes the game uses
#   5. Newton-sqrt (3 divisions) vs a division-free bitwise sqrt
#      (the _draw_enemy_radar pattern)
#   6. The MPZ path: `//` when the operand is >= 2^30 - the only case
#      where division really allocates (and the only case where the
#      audit's GC-churn argument can hold at all)
#
# RUN: open in Thonny, set PLATFORM, F5. Takes ~1 min. PASTE OUTPUT BACK.
#
# HONESTY NOTE: Thonny runs this as bytecode; the deployed game's //
# lives in @micropython.native machine code (a direct C call into the
# same 32-bit divide). Ranking transfers; absolute ns are a little
# pessimistic (bytecode adds VM dispatch).

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

# ---------- SET THIS TO MATCH THE DEVICE YOU ARE ON ----------
PLATFORM = 'thumbycolor'   # or 'thumby'
N = 4096                   # iterations per measurement

if PLATFORM == 'thumby':
    SPACE_W = 2047
    Z_DIST = 30
else:
    SPACE_W = 2559
    Z_DIST = 50

# ---------- device identity ----------
print('== bench_div v2 ==')
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
    print('NOTE: gc.mem_free/alloc not available here - MPZ churn skipped')


def gc_freed():
    # this firmware's gc.collect() returns None, not a count
    r = gc.collect()
    return 0 if r is None else r


if HAVE_MEMAPI:
    print('NOTE: this build may return None from gc.collect() - '
          'churn counts marked n/a where unavailable')

# ---------- small-int probe ----------
# IMPORTANT: the allocation must be measured at CREATION time. Storing an
# already-built value (in a list slot) never allocates, so a probe of
# pre-built values proves nothing.
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
        ('2^29-1',  lambda: (1 << s29) - 1),
        ('2^29',    lambda: 1 << s29),
        ('2^30-1',  lambda: (1 << s30) - 1),
        ('2^30',    lambda: 1 << s30),
        ('-(2^30)', lambda: -(1 << s30)),
        ('2^40',    lambda: 1 << s40),
    ]:
        print('  %7s : %d B' % (nm, create_bytes(mk)))
    w = SPACE_W               # built at runtime -> not constant-folded
    print('  %d<<19 : %d B  <- (x<<3) fed to project() for an extreme x on this platform' %
          (w, create_bytes(lambda: w << 19)))

# ---------- timing helper ----------


def bench(fn):
    # fn(i) must not return None; N rotations over rotating operands
    acc = 0
    t0 = ticks_us()
    for i in range(N):
        acc ^= fn(i)
    dt = ticks_diff(ticks_us(), t0)
    return (dt * 1000) // N, acc


# 16 real-range 16.16 operands (all < 2^30 -> small ints on this build),
# 8 positive / 8 negative, masked by i & 15
X = array('l', [1000, 65536, 262144, 1048576, 4194304, 16777216,
                67108864, 134217728,
                -1000, -65536, -262144, -1048576, -4194304, -16777216,
                -67108864, -134217728])

# every divisor the game actually uses (see the inventory in the report)
DIVS = [2, 3, 4, 5, 10, 12, 15, 50,
        128, 256, 512,            # fpdiv_a's effective divisors: powers of 2
        700,                      # radar height
        13107, 52429, 72090, 113377,   # fpmul(72090, z)-style numerators
        3932160, 1000000]         # 60<<16, ticks->fp


def is_pow2(d):
    return d != 0 and (d & (d - 1)) == 0


def log2(d):
    k = 0
    t = 1
    while t < d:
        t <<= 1
        k += 1
    return k


print('')
print('--- division on small ints (N=%d ops, ns/op) ---' % N)
print('  divisor     //     %%    >>    magic  (>> and magic: pow-2 only)')
for d in DIVS:
    ns_div, _ = bench(lambda i: X[i & 15] // d)
    ns_mod, _ = bench(lambda i: X[i & 15] % d)
    sh = '-'
    mg = '-'
    if is_pow2(d):
        k = log2(d)
        ns_sh, _ = bench(lambda i: X[i & 15] >> k)
        ok = True
        for x in X:
            if (x // d) != (x >> k):
                ok = False
        sh = '%d%s' % (ns_sh, '' if ok else '!')
        # magic-number multiply + shift sized for x < 2^28 (game max ~2^27.3)
        xb = 28
        k2 = 0
        t = 1
        while t < d:
            t <<= 1
            k2 += 1
        k = xb + k2
        m = ((1 << k) - 1) // d + 1     # ceil(2^k / d)
        bad = 0
        # verify over a spread of the game's operand range
        for j in range(2000):
            xx = (j * 65537) & ((1 << xb) - 1)
            if (xx * m) >> k != xx // d:
                bad += 1
        if bad:
            mg = 'BAD(%d)' % bad
        else:
            ns_mg, _ = bench(lambda i: (X[i & 15] * m) >> k)
            mg = str(ns_mg)
    print('  %9d  %6d  %6d  %5s  %8s' % (d, ns_div, ns_mod, sh, mg))

# ---------- variable divisor (the project()/fpdiv real-world case) ----------
print('')
print('--- variable divisor: x // y, both from real 16.16 ranges ---')
Y = array('l', [240, 1024, 4096, 8192, 16384, 20868,
                65536, 3932160])      # (z>>3)-style values, 60<<16
ns_var, _ = bench(lambda i: X[i & 15] // Y[i & 7])
print('  x // y          : %d ns' % ns_var)
ns_var2, _ = bench(lambda i: X[i & 15] // (i + 97))   # worst case: divisor changes every op
print('  x // (i+97)     : %d ns  (divisor changes each op)' % ns_var2)

# ---------- the game's fpdiv/fpdiv_a whole expression ----------
print('')
print('--- fpdiv as written: a if (b>>3)==0 else ((a<<3)//(b>>3))<<10 ---')


def fpdiv_full(a, b):
    return a if (b >> 3) == 0 else ((a << 3) // (b >> 3)) << 10


def fpdiv_a_full(a, b):
    return ((a << 4) // (b >> 4)) << 8


# b values exactly as the game builds them:
#   stars:  b = fpmul(72090, z)  = 282 * (z>>8),  z in 5..50 <<16
#   lasers: b = fpmul(13107|52429, z), z in 8..60 <<16
#   getSprite: 60<<16, drawSpriteWithScale: 256<<16, project: z itself
A = SPACE_W << 16                       # worst-case operand on this platform
B_CASES = [
    ('stars z=5',   282 * ((5 << 16) >> 8)),
    ('stars z=50',  282 * ((50 << 16) >> 8)),
    ('laser z=8',   51 * ((8 << 16) >> 8)),
    ('laser z=60',  205 * ((60 << 16) >> 8)),
    ('getSprite',   60 << 16),
    ('scaled sprite', 256 << 16),
    ('project z=70',  70 << 16),
    ('ticks->fp',   1000000),
]
for nm, b in B_CASES:
    ns, _ = bench(lambda i: fpdiv_full(A, b))
    print('  fpdiv(a=%d, b=%s=%d): %d ns' % (A, nm, b, ns))
for nm, b in [('physics t=100000', 100000), ('physics t=65536', 65536)]:
    ns, _ = bench(lambda i: fpdiv_a_full(1000000, b))
    print('  fpdiv_a(a=1e6, b=%s=%d): %d ns' % (nm, b, ns))

# ---------- sqrt: Newton (3 divisions) vs division-free bitwise ----------
print('')
print('--- sqrt: newton (3 //) vs bitwise (no //) ---')


def sqrt_newton(zd):
    rd = (zd >> 10) + 1
    rd = (rd + zd // rd) >> 1
    rd = (rd + zd // rd) >> 1
    rd = (rd + zd // rd) >> 1
    return rd


def sqrt_bit(zd):
    n = zd
    r = 0
    bit = 1 << 30
    while bit > n:
        bit >>= 2
    while bit:
        t = r + bit
        if n >= t:
            n -= t
            r = (r >> 1) + bit
        else:
            r >>= 1
        bit >>= 2
    return r


# zd values the radar actually sees: zd = abs(e[2])+1 and enemies despawn
# at z = 60<<16, so zd <= 60<<16+1. (Beyond that the 3 newton iterations
# no longer converge - but the game never feeds them values like that.)
ZDS = [129, (1 << 16) + 1, (10 << 16) + 1, (20 << 16) + 1,
       (40 << 16) + 1, (60 << 16) + 1]
worst = 0
for zd in ZDS:
    d = sqrt_newton(zd) - sqrt_bit(zd)
    if d < 0:
        d = -d
    if d > worst:
        worst = d
print('  max |newton - bitwise| over %d in-range zd values: %d' % (len(ZDS), worst))
ns_nw, _ = bench(lambda i: sqrt_newton(ZDS[i & 5]))
ns_bt, _ = bench(lambda i: sqrt_bit(ZDS[i & 5]))
print('  newton (3 div)  : %d ns' % ns_nw)
print('  bitwise (no div): %d ns' % ns_bt)

# ---------- the MPZ path: operands >= 2^30 ----------
print('')
print('--- big ints (>= 2^30): the MPZ bignum division path ---')
s27, s32, s40 = 27, 32, 40
x27 = 1 << s27        # largest-ish small int in the game
x32 = 1 << s32
x40 = 1 << s40
ns_small, _ = bench(lambda i: x27 // 1000000)
ns_32, _ = bench(lambda i: x32 // 1000000)
ns_40, _ = bench(lambda i: x40 // 1000000)
# which of these is a small int is settled by the probe at the top:
# on a 32-bit build 2^27 is small, 2^32/2^40 are MPZ bignums.
print('  2^27  // 1000000 : %d ns   (see probe: small or bignum?)' % ns_small)
print('  2^32  // 1000000 : %d ns' % ns_32)
print('  2^40  // 1000000 : %d ns' % ns_40)
if HAVE_MEMAPI:
    if gc_freed() is not None:
        gc.collect()
        for _ in range(500):
            x32 // 1000000
        freed_big = gc_freed()
        gc.collect()
        for _ in range(500):
            x27 // 1000000
        freed_small = gc_freed()
        if freed_big or freed_small:
            print('  objects freed per 500 ops:  small %d,  2^32 %d  '
                  '(2/op = quotient+remainder MPZs)' % (freed_small, freed_big))
        else:
            print('  churn: gc.collect() returns None on this build - '
                  'no freed-object count available')

print('')
print('== done. Paste this whole output back. ==')
