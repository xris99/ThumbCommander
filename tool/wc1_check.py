#!/usr/bin/env python3
"""
Smoke test over every mission of every converted campaign.

For each mission it builds the flight exactly as the game does, then
lets a simple pilot fly the objectives in order (autopilot, fight,
move on), draws a frame in every action sphere and settles the
objectives. Nothing is asserted about who wins - the point is that no
mission, ship type, sprite set or AI branch raises, and that the
mission records parse into something flyable.

Usage:
    python3 tool/wc1_check.py              # all campaigns
    python3 tool/wc1_check.py --campaign 0 --turns 400 -v
"""

import argparse
import os
import random
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = os.path.join(REPO_ROOT, 'games', 'wingcommander')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign', type=int, default=-1)
    ap.add_argument('--turns', type=int, default=500,
                    help='game turns flown per action sphere')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    sys.path.insert(0, REPO_ROOT)
    from thumby_engine.pc import bootstrap
    bootstrap(local_root=GAME_DIR, mode='color')
    sys.path.insert(0, GAME_DIR)
    random.seed(7)

    import campaign
    import flight
    import ui
    import wcdata as D
    import wcmath as M
    import world as W

    T = D.Types()
    A = D.Ai()
    pal = bytearray(D.load('pal.wc'))
    fonts = (D.Font(2), D.Font(1))
    ui.setup(fonts[0], fonts[1], pal)
    flown = 0
    failed = 0
    types_seen = set()
    results = {}
    for c in range(3):
        if (args.campaign != -1 and c != args.campaign) or \
                not D.exists('mod%d.wc' % c):
            continue
        camp = D.Campaign(c)
        for series in range(1, 16):
            for mission in range(4):
                mis = D.Mission(c, series, mission)
                if not mis.valid:
                    continue
                tag = 'campaign %d series %2d mission %d (%s)' % (
                    c, series, mission, mis.series_name.decode('latin1'))
                try:
                    st = campaign.State(A)
                    st.campaign = c
                    st.series = series
                    st.mission = mission
                    for cockpit in (1, 0):
                        fl = flight.Flight(T, A, fonts, pal, st,
                                           D.Mission(c, series, mission),
                                           {'cockpit': cockpit})
                        fl.draw()
                    w = fl.w
                    p = w.o[0]
                    for leg in range(len(w.mis.objectives) + 1):
                        if w.result:
                            break
                        if not w.enemies_left() and w.autopilot_ok() == 0:
                            w.autopilot()
                        for ob in w.o:
                            if ob.cls >= W.C_SHIP:
                                types_seen.add(ob.typ)
                        for turn in range(args.turns):
                            if w.result:
                                break
                            e = fl.brain.scan_for_enemy(p, 30000)
                            if e != -1:
                                t = w.o[e]
                                p.target = e
                                x, y, z = t.x, t.y, t.z
                            else:
                                x, y, z = w.objective_pos(w.dest)
                            lx, ly, lz = M.to_frame(
                                p.m, (x - p.x) >> 8, (y - p.y) >> 8,
                                (z - p.z) >> 8)
                            yw, pt = M.spherical(lx, ly, lz)
                            p.ry = max(-8, min(8, -yw))
                            p.rp = max(-8, min(8, -pt))
                            w.celerate(p, 0x100)
                            if e != -1 and abs(yw) < 5 and abs(pt) < 5:
                                w.fire_guns(p)
                                if turn % 40 == 0:
                                    w.fire_missile(p)
                            w.update()
                            if w.tick % 8 == 0:
                                w.check_sphere()
                            if turn % 97 == 0:
                                fl.draw()
                            del w.messages[:]
                            del w.sfx[:]
                            if e == -1 and turn > 40 and \
                                    w.autopilot_ok() == 0:
                                break
                        fl.draw()
                    w.cleanup_objectives()
                    out = campaign.post_mission(st, camp, w,
                                                campaign.Outcome())
                    results[w.result] = results.get(w.result, 0) + 1
                    flown += 1
                    if args.verbose:
                        print('ok   %s: result %d, %d turns, kills %d+%d, '
                              'score %d/%d' % (tag, w.result, w.tick,
                                               w.kills, w.wing_kills,
                                               out.score, out.full_score))
                except Exception:       # noqa: BLE001
                    import traceback
                    failed += 1
                    print('FAIL', tag)
                    traceback.print_exc()
    names = sorted(T.names[t].decode('latin1') for t in types_seen)
    print('%d missions flown, %d failed; flight results %s' % (
        flown, failed, results))
    print('ship types met: ' + ', '.join(names))
    sys.exit(1 if failed or not flown else 0)


if __name__ == '__main__':
    main()
