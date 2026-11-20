# wcmath.py - integer vector math for the Wing Commander flight model.
#
# Conventions are the ones of the original game (wc1-re src/geom.c):
#   * a left-handed frame: x right, y up, z forward;
#   * angles are whole degrees;
#   * positions and velocities are 24.8 fixed point world units;
#   * an orientation is three unit vectors (right, up, forward). They are
#     kept here as one flat list of nine ints with 14 fractional bits:
#         m = [rx, ry, rz,  ux, uy, uz,  fx, fy, fz]
#     (the original uses 8 bits and re-normalises every turn; 14 bits
#     keep every product inside a MicroPython small int).
#
# Everything is plain integer code so the simulation allocates nothing
# per call except where a result tuple is returned.

from array import array
from math import sin, pi, atan2, sqrt

ONE = 16384
R = 0
U = 3
F = 6

SIN = array('h', [int(round(sin(i * pi / 180) * 16384)) for i in range(360)])


def isin(a):
    return SIN[a % 360]


def icos(a):
    return SIN[(a + 90) % 360]


def identity(m):
    m[0] = ONE; m[1] = 0; m[2] = 0
    m[3] = 0; m[4] = ONE; m[5] = 0
    m[6] = 0; m[7] = 0; m[8] = ONE


@micropython.native
def _rot(m, a, b, deg):
    # va' = va*cos - vb*sin ; vb' = va*sin + vb*cos
    s = SIN[deg % 360]
    c = SIN[(deg + 90) % 360]
    i = 0
    while i < 3:
        x = m[a + i]
        y = m[b + i]
        m[a + i] = (x * c - y * s) >> 14
        m[b + i] = (x * s + y * c) >> 14
        i += 1


def pitch(m, deg):
    """alter_pitch: positive raises the nose."""
    _rot(m, U, F, deg)


def yaw(m, deg):
    """alter_yaw: positive turns the nose to the left."""
    _rot(m, F, R, deg)


def roll(m, deg):
    _rot(m, R, U, deg)


@micropython.native
def fix(m):
    """fix_objects_ijk: re-orthonormalise (right = up x forward, ...)."""
    ux = m[3]; uy = m[4]; uz = m[5]
    fx = m[6]; fy = m[7]; fz = m[8]
    rx = (uy * fz - uz * fy) >> 14
    ry = (uz * fx - ux * fz) >> 14
    rz = (ux * fy - uy * fx) >> 14
    ux = (fy * rz - fz * ry) >> 14
    uy = (fz * rx - fx * rz) >> 14
    uz = (fx * ry - fy * rx) >> 14
    n = sqrt(rx * rx + ry * ry + rz * rz)
    if n > 0:
        n = 16384 / n
        m[0] = int(rx * n); m[1] = int(ry * n); m[2] = int(rz * n)
    n = sqrt(ux * ux + uy * uy + uz * uz)
    if n > 0:
        n = 16384 / n
        m[3] = int(ux * n); m[4] = int(uy * n); m[5] = int(uz * n)
    n = sqrt(fx * fx + fy * fy + fz * fz)
    if n > 0:
        n = 16384 / n
        m[6] = int(fx * n); m[7] = int(fy * n); m[8] = int(fz * n)


def copy(src, dst):
    for i in range(9):
        dst[i] = src[i]


@micropython.native
def mag(x, y, z):
    """Vector length; float sqrt keeps the squares out of big ints."""
    x = x * 1.0
    y = y * 1.0
    z = z * 1.0
    return int(sqrt(x * x + y * y + z * z))


@micropython.native
def dot(m, o, x, y, z):
    """(x, y, z) . row o of m, result in the units of the vector."""
    return (x * m[o] + y * m[o + 1] + z * m[o + 2]) >> 14


@micropython.native
def to_frame(m, x, y, z):
    """transform_to_objects_frame: world vector -> (right, up, forward)."""
    return ((x * m[0] + y * m[1] + z * m[2]) >> 14,
            (x * m[3] + y * m[4] + z * m[5]) >> 14,
            (x * m[6] + y * m[7] + z * m[8]) >> 14)


def spherical(x, y, z):
    """rectangular_to_spherical -> (yaw, pitch) in degrees. yaw is
    positive to the right, pitch is negative above the horizon (the
    original computes acos(y / r) - 90)."""
    planar = sqrt(x * 1.0 * x + z * 1.0 * z)
    if planar == 0 and y == 0:
        return 0, 0
    return (int(round(atan2(x, z) * 57.29578)),
            -int(round(atan2(y, planar) * 57.29578)))


def angle_cw(px, py):
    """Clockwise screen angle (degrees, 0..359) of the vector (px, py)."""
    if px == 0 and py == 0:
        return 0
    return int(round(atan2(px, py) * 57.29578)) % 360


def wrap(deg):
    """WrapDegrees -> -180..180."""
    deg %= 360
    if deg > 180:
        deg -= 360
    return deg
