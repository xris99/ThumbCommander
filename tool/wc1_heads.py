#!/usr/bin/env python3
"""
Self-running check of the converted talking-head assets (docs/05 5.7).

Validates every head<NN>.wc and bdrop.wc in games/wingcommander/assets
without importing the game: the magic and header, the patch rectangles
inside the 128 x 62 picture, the file size the header implies, a
transparent border around the head and visible content in every
patch. Run it after every conversion:

    python3 tool/wc1_heads.py [--assets DIR]
"""

import argparse
import glob
import os
import struct
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ASSETS = os.path.join(REPO_ROOT, 'games', 'wingcommander',
                              'assets')

PIC_W, PIC_H = 128, 62
BD_SIZE = PIC_W * PIC_H


def nonblack(buf):
    return sum(1 for b in buf if b)


def check_head(path, problems):
    name = os.path.basename(path)
    face = int(name[4:6])
    with open(path, 'rb') as f:
        d = f.read()

    def bad(msg):
        problems.append('%s: %s' % (name, msg))

    if len(d) < 16:
        bad('shorter than the header')
        return
    if d[:4] != b'WCH1':
        bad('magic %r' % d[:4])
        return
    if d[4] != 0 or d[5] != 0:
        bad('reserved header bytes set')
    w, h = d[6], d[7]
    if (w, h) != (PIC_W, PIC_H):
        bad('canvas %d x %d, expected %d x %d' % (w, h, PIC_W, PIC_H))
    mouth = struct.unpack_from('<4B', d, 8)
    eye = struct.unpack_from('<4B', d, 12)
    for label, r in (('mouth', mouth), ('eye', eye)):
        x, y, rw, rh = r
        if x + rw > PIC_W or y + rh > PIC_H:
            bad('%s rect %s off the picture' % (label, r))
    size = 16 + w * h + 10 * mouth[2] * mouth[3] + 10 * eye[2] * eye[3]
    if len(d) != size:
        bad('file is %d bytes, header implies %d' % (len(d), size))
        return
    base = d[16:16 + w * h]
    nz = nonblack(base)
    if nz < 500:
        bad('head has only %d visible pixels' % nz)
    if nz == w * h:
        bad('no transparent border: index 0 never appears')

    off = 16 + w * h
    m_area = mouth[2] * mouth[3]
    for label, r, start in (('mouth', mouth, off),
                            ('eye', eye, off + 10 * m_area)):
        x, y, rw, rh = r
        area = rw * rh
        sub = bytearray()
        for row in range(y, y + rh):
            sub += d[16 + row * w + x:16 + row * w + x + rw]
        differs = 0
        zeros = 0
        for i in range(10):
            p = d[start + i * area:start + (i + 1) * area] if area else b''
            if nonblack(p) == 0:
                zeros += 1
            elif p != sub:
                differs += 1
        if zeros == 10:
            bad('%s: every patch empty' % label)
        elif differs == 0 and zeros < 10:
            bad('%s patches never change the picture' % label)
        if zeros:
            print('     %s: %d zero patches'
                  % (label, zeros))
    print('head %2d: mouth %s eye %s, base %d/%d visible, %d bytes'
          % (face, mouth, eye, nz, w * h, len(d)))
    return len(d)


def check_bdrop(path, problems):
    with open(path, 'rb') as f:
        d = f.read()
    if d[:4] != b'WBD1':
        problems.append('bdrop.wc: magic %r' % d[:4])
        return
    n = d[4]
    if len(d) != 5 + 2 * n + n * BD_SIZE:
        problems.append('bdrop.wc: %d bytes, %d frames imply %d'
                        % (len(d), n, 5 + 2 * n + n * BD_SIZE))
        return
    stars = 0
    for i in range(n):
        key, flags = struct.unpack_from('<BB', d, 5 + 2 * i)
        frame = d[5 + 2 * n + i * BD_SIZE:5 + 2 * n + (i + 1) * BD_SIZE]
        if nonblack(frame) < 100:
            problems.append('bdrop.wc frame %d (kind %d char %d): '
                            'only %d visible pixels'
                            % (i, key >> 4, key & 15, nonblack(frame)))
        stars += flags & 1
    print('bdrop: %d frames (%d with baked stars), %d bytes'
          % (n, stars, len(d)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--assets', default=DEFAULT_ASSETS)
    args = ap.parse_args()

    problems = []
    sizes = []
    for path in sorted(glob.glob(os.path.join(args.assets, 'head*.wc'))):
        sizes.append(check_head(path, problems))
    wc1 = sum(s for s in sizes)   # every built face; SM2 adds two more
    bdrop = os.path.join(args.assets, 'bdrop.wc')
    if os.path.exists(bdrop):
        check_bdrop(bdrop, problems)
    else:
        problems.append('bdrop.wc missing')

    print('heads: %d files, %.1f KB total (WC1 alone would be 11)'
          % (len(sizes), wc1 / 1024.0))
    if problems:
        print('FAILED:')
        for p in problems:
            print('  ' + p)
        sys.exit(1)
    print('OK')


if __name__ == '__main__':
    main()
