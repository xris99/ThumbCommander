#!/usr/bin/env python3
"""Does the device scene interpreter agree with the reference?

docs/06 Check: every object position of every animation of every
MIDGAME scene must agree with the reference interpreter (tool/wc1/
refscene.py, run on the UNSCALED disk data) at every step, within one
device pixel.

Both interpreters are driven through a whole variant exactly the way
scene.show() drives the device: one persistent object table per variant
across the packet's records (animation numbers are replayed pervasively
and only the script cursor is rebound per call, logic.c:2616-2627),
stepped until the animation completes, W global wait counted down the
same way on both sides. So this check compares the replay-persistent
state (delay, repeat group, accumulated positions) as well as the
fresh one.

--preview additionally runs the real scene.show() for every scene /
variant with the step clock fast-forwarded and writes a PNG strip of
the distinct frames into /tmp/wc1_scene_previews (docs/06 "PNG strips").
"""

import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

REPO = '/Users/christian/Source/coding/ThumbCommander/ThumbCommander'
GAME_DIR = os.path.join(REPO, 'games', 'wingcommander')
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'tool'))

# The converter and the wc1 package import numpy at module import time,
# so they must be loaded before bootstrap() puts the PC shim modules on
# sys.path (the fake _thread would break numpy's warnings import).
import numpy as np
from PIL import Image
# Image.save() pulls in PngImagePlugin lazily, which imports logging,
# which needs the real time module - all of that has to happen before
# bootstrap() installs the stubs (same fix as tool/wc1_selfplay.py).
from PIL import PngImagePlugin      # noqa: F401
import logging                      # noqa: F401

import wc1_convert as wc
from wc1 import refscene, gfx
from struct import unpack_from

from thumby_engine.pc import bootstrap
bootstrap(local_root=GAME_DIR, mode='color')
sys.path.insert(0, GAME_DIR)

import wcdata as D
import ui
import scene
import campaign

SRC = '/Users/christian/Documents/WC1/WC/WING'

# one device pixel of slack: docs/06 acceptance is position agreement,
# not pixel-exact rasterisation (positions share the original pixel
# space; the device rounds them to device pixels at the draw site
# while the reference's scaled position stays fractional)
PX = 128.0
STEP_CAP = 20000


def drive_pair(objs, ins, ninstrs, per, anim, defs, refs):
    """Run one PlaySceneAnimation on both interpreters over the same
    persistent tables and compare them step by step. Returns the worst
    errors in device pixels (object x, object y, draw x, draw y), the
    number of steps and the first disagreement."""
    a = scene.Animation(objs, ins, ninstrs, per, anim)
    r = refscene.RefAnimation(defs, refs, anim)
    assert (a.lo, a.hi) == (r.lo, r.hi), (anim, a.lo, r.lo, per)

    # the initial state must match as well: the converter zeroed the
    # runtime slots because the shipped data starts every object that
    # way (probe: delay, goals and deltas are all zero)
    for i in range(a.lo, a.hi):
        d, o = objs[i], refs[i]
        assert d[0] == o['x'] and d[1] == o['y'], (anim, i)
        assert d[2] == o['scale'] and d[3] == o['rotation'], (anim, i)
        assert d[4] == o['frame'] & 0xFF and d[5] == o['layer'], \
            (anim, i, d[4], o['frame'])
        assert d[16] == o['goalFlags'] and d[17] == o['delay'], \
            (anim, i, d[16], o['goalFlags'])

    dev = []

    def draw(obj, x8, y8, fbyte):
        dev.append((obj[5], fbyte, x8, y8))

    # RefAnimation.step records nothing in its own draws list - the
    # frames the original draws arrive through the draw callback only
    # (converter learning pass does the same, wc1_convert.py:953-958)
    ref = []

    def ref_draw(layer, frame, x, y):
        ref.append((layer, frame & 0xFF, x, y))

    worst = [0.0] * 4                     # x, y, draw x, draw y
    bad = None
    steps = 0
    r_done = None                         # step the reference finished
    while a.complete == 0:
        dev.clear()
        ref.clear()
        a.step(draw)
        r.step(ref_draw)
        steps += 1
        if r_done is None and r.complete != 0:
            r_done = steps

        # after the reference finished the original PlaySceneAnimation
        # would have returned. Goal tests are exact integer comparisons
        # in the shared original pixel space, so the device finishes on
        # the same step; this guard only exists so a lagging device (a
        # regression) is not miscompared while still moving.
        if r_done is not None:
            continue

        for i in range(a.lo, a.hi):
            d, o = objs[i], refs[i]
            # positions share the original pixel space on both sides,
            # so agreement is an integer comparison; the slack is
            # stated in device pixels
            e = abs(d[0] - o['x']) * gfx.SCREEN_SX
            if e > worst[0]:
                worst[0] = e
                if e > 1.0 and bad is None:
                    bad = ('x over 1 px', anim, steps, i,
                           d[0], o['x'], round(e, 3))
            e = abs(d[1] - o['y']) * gfx.SCREEN_SY
            if e > worst[1]:
                worst[1] = e
                if e > 1.0 and bad is None:
                    bad = ('y over 1 px', anim, steps, i,
                           d[1], o['y'], round(e, 3))
            if d[2] != o['scale'] or d[3] != o['rotation'] or \
                    d[4] != o['frame'] & 0xFF or d[17] != o['delay']:
                if bad is None:
                    bad = ('state', anim, steps, i,
                           d[2:5], d[17],
                           o['scale'], o['rotation'], o['frame'],
                           o['delay'])

        if len(dev) != len(ref):
            if bad is None:
                bad = ('draw count', anim, steps, len(dev), len(ref),
                       dev, ref)
        else:
            for j, ((l1, f1, x8, y8), (l2, f2, x, y)) in \
                    enumerate(zip(dev, ref)):
                if (l1 != l2 or f1 != f2) and bad is None:
                    bad = ('draw entry', anim, steps, j,
                           (l1, f1, x8, y8), (l2, f2, x, y))
                # draw positions are compared in 8.7 space like the
                # object positions: the +64//128 rounding to integer
                # device pixels happens in _Drawer (scene.py:319-320),
                # counting it here would add a constant half pixel to
                # every draw error. i*320 original px and i*128 device
                # px are the same distance, so the group offsets cancel
                e = abs(x8 / PX - x * gfx.SCREEN_SX)
                if e > worst[2]:
                    worst[2] = e
                    if e > 1.0 and bad is None:
                        bad = ('draw x over 1 px', anim, steps, j,
                               (x8, y8), (x, y), round(e, 3))
                e = abs(y8 / PX - y * gfx.SCREEN_SY)
                if e > worst[3]:
                    worst[3] = e
                    if e > 1.0 and bad is None:
                        bad = ('draw y over 1 px', anim, steps, j,
                               (x8, y8), (x, y), round(e, 3))

        if steps > STEP_CAP:
            raise RuntimeError('animation %d never completes' % anim)

    # the device finished; measure how far the reference finished from
    # it. With integer goal tests in the shared original pixel space
    # both interpreters must complete on the same step - any lag is a
    # disagreement.
    if r.complete == 0:
        lag = 0
        while r.complete == 0 and lag < STEP_CAP:
            ref.clear()
            r.step(ref_draw)
            lag += 1
        if r.complete == 0:
            raise RuntimeError('reference animation %d never '
                               'completes' % anim)
    else:
        lag = steps - r_done
    if lag > 0 and bad is None:
        bad = ('completion lag %d steps' % lag, anim, steps)
    if lag == 0:
        # both count the W global wait down identically; finishing on
        # the same step must report the same globals
        assert a.state == [r.state['delayFrames'],
                           r.state['waitCommand']], (anim, a.state,
                                                     r.state)
    return worst, steps, lag, bad


def check_variant(conv, scene_no, v):
    S = D.Scene(scene_no)
    per, nanim, ninstrs, objs, ins, tbl, pkt = scene.load_variant(S, v)
    pk = conv.packet('MIDGAME.V%02d' % scene_no)
    defs = pk.section(v + 1)
    if defs:
        r_per, count, refs = refscene.read_disk_objects(defs)
        assert r_per == per, (scene_no, v, r_per, per)
        assert count == len(objs), (scene_no, v, count, len(objs))
        assert nanim * per == count, (scene_no, v, nanim, per, count)
    else:
        assert (per, nanim) == (0, 0), (scene_no, v)
        refs = []

    worst = [0.0] * 4
    recs = steps = 0
    lag_max = lagged = 0
    bad = None
    if pkt:
        o = unpack_from('<I', pkt, 0)[0]
        while True:
            shot = unpack_from('<b', pkt, o)[0]
            if shot == -2:
                break
            o += 13
            anim = shot - 50
            if defs and 0 <= anim < nanim:
                recs += 1
                w, st, lag, b = drive_pair(objs, ins, ninstrs, per, anim,
                                           defs, refs)
                steps += st
                for j in range(4):
                    if w[j] > worst[j]:
                        worst[j] = w[j]
                if lag > lag_max:
                    lag_max = lag
                if lag:
                    lagged += 1
                if b is not None and bad is None:
                    bad = b
    if bad is not None:
        print('scene %d v%d FAIL: %s' % (scene_no, v, bad))
        return False
    print('scene %d v%d: %d records %d steps; max err x %.3f y %.3f '
          'draw %.3f/%.3f px; completion lag %d steps in %d anims' %
          (scene_no, v, recs, steps,
           worst[0], worst[1], worst[2], worst[3], lag_max, lagged))
    return True


# --- preview ----------------------------------------------------------------

def rgb565(fb):
    v = np.frombuffer(bytes(fb), dtype='<u2').reshape(128, 128)
    r = (v >> 11) * 255 // 31
    g = ((v >> 5) & 0x3F) * 255 // 63
    b = (v & 0x1F) * 255 // 31
    return np.dstack([r, g, b]).astype(np.uint8)


class Strip:
    """Collects every distinct framebuffer between two display.update
    calls - that is one step of PlaySceneAnimation on the device."""

    def __init__(self):
        self.frames = []
        self.last = None

    def update(self):
        fb = bytes(scene.display.buffer)
        if fb != self.last:
            self.last = fb
            self.frames.append(fb)

    def save(self, path):
        if not self.frames:
            return
        n = len(self.frames)
        strip = np.zeros((128, 128 * n + n - 1, 3), dtype=np.uint8)
        x = 0
        for fr in self.frames:
            strip[:, x:x + 128] = rgb565(fr)
            x += 129
        Image.fromarray(strip).save(path)


def preview():
    """Run the real show() with the step clock fast-forwarded: the PC
    has no reason to wait for 62 ms frames or for a human to let go of
    the buttons."""
    ui.setup(D.Font(2), D.Font(1), bytearray(D.load('pal.wc')))
    ai = D.Ai()
    st = campaign.State(ai)
    scene.ticks_diff = lambda a, b: 10 ** 9
    out = '/tmp/wc1_scene_previews'
    os.makedirs(out, exist_ok=True)
    total = 0
    for scene_no in range(9):
        if not D.exists('mid%02d.wc' % scene_no):
            continue
        for v in range(2):
            strip = Strip()
            scene.display.update = strip.update
            scene.show(scene_no, v, st, ai, None, None)
            path = os.path.join(out, 'scene%d_v%d.png' % (scene_no, v))
            strip.save(path)
            total += len(strip.frames)
            print('%s: %d frames' % (path, len(strip.frames)))
    print('previews written: %d frames total' % total)


def main():
    conv = wc.Converter(SRC, '/tmp/wc1_scene_tmp', preview=False,
                        verbose=False)
    ok = True
    for scene_no in range(9):
        if not D.exists('mid%02d.wc' % scene_no):
            print('scene %d: no converted block' % scene_no)
            continue
        S = D.Scene(scene_no)
        for v in range(S.nvar):
            ok = check_variant(conv, scene_no, v) and ok
    print('POSITION AGREEMENT ' + ('OK' if ok else 'FAILED'))
    if '--preview' in sys.argv:
        preview()


main()
