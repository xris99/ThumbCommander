#!/usr/bin/env python3
"""
Headless end-to-end run of games/wingcommander on the PC emulation.

Plays a whole sortie the way a player would - through the buttons, not
by calling into the game: title -> new campaign -> briefing -> launch ->
autopilot from nav point to nav point, dogfighting whatever is there ->
landing -> debriefing -> mission report -> save -> exit. The run fails
(exit code 1) if the game raises, if the flight does not end within the
frame budget, or if the saved game does not show the mission as flown.

It needs the converted game data in games/wingcommander/assets (see
tool/wc1_convert.py). Screenshots of the stages are written to
build/wc1_selfplay/ so the pictures can be checked by eye.

Usage:
    python3 tool/wc1_selfplay.py            # first mission
    python3 tool/wc1_selfplay.py --seed 7 --max-frames 9000
"""

import argparse
import json
import os
import random
import struct
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = os.path.join(REPO_ROOT, 'games', 'wingcommander')
OUT_DIR = os.path.join(REPO_ROOT, 'build', 'wc1_selfplay')
BTN = ('A', 'B', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'LB', 'RB', 'MENU')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--max-frames', type=int, default=12000)
    ap.add_argument('--keep-save', action='store_true')
    args = ap.parse_args()

    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    sys.path.insert(0, REPO_ROOT)
    from thumby_engine.pc import bootstrap
    bootstrap(local_root=GAME_DIR, mode='color')
    sys.path.insert(0, GAME_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in os.listdir(OUT_DIR):
        if name.endswith('.png'):
            os.remove(os.path.join(OUT_DIR, name))
    random.seed(args.seed)

    save_path = os.path.join(GAME_DIR, 'wc_save.json')
    backup = None
    if os.path.exists(save_path):
        with open(save_path) as f:
            backup = f.read()
        os.remove(save_path)

    import engine as eng
    import thumbyButton as tb
    eng.fps_limit(0)                       # run as fast as the PC goes
    import thumby_engine.platform as plat
    plat.display.setFPS = lambda fps: None

    import flight
    import campaign
    import wcmath as M
    import world as W

    state = {'frame': 0, 'flight': None, 'saves': 0, 'shots': 0,
             'phase': 'menus', 'done_at': None, 'flight_frames': 0,
             'last_shot': -999, 'auto_wait': 0, 'log': []}

    real_init = flight.Flight.__init__

    def init(self, *a, **k):
        real_init(self, *a, **k)
        state['flight'] = self
        state['phase'] = 'flight'
        print('[selfplay] flight started at frame', state['frame'])
    flight.Flight.__init__ = init

    real_save = campaign.State.save

    def save(self):
        state['saves'] += 1
        return real_save(self)
    campaign.State.save = save

    def shot(name):
        try:
            from PIL import Image
        except ImportError:
            return
        b = bytes(plat.display.buffer)
        px = []
        for i in range(0, len(b), 2):
            v = b[i] | b[i + 1] << 8
            px.append((((v >> 11) & 31) * 255 // 31,
                       ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))
        im = Image.new('RGB', (128, 128))
        im.putdata(px)
        im.resize((384, 384), Image.NEAREST).save(
            os.path.join(OUT_DIR, '%02d_%s.png' % (state['shots'], name)))
        state['shots'] += 1

    def fly(pressed):
        """Bang-bang pilot working only from what the game exposes."""
        fl = state['flight']
        w = fl.w
        p = w.o[0]
        state['flight_frames'] += 1
        if w.result != 0:
            return
        # once per run: open the flight computer and the nav map
        f = state['flight_frames']
        if not state.get('paused') and 60 <= f < 100:
            if f == 60:
                pressed['MENU'] = True
            elif f == 66:
                shot('computer')
                pressed['DOWN'] = True
            elif f == 70:
                pressed['DOWN'] = True
            elif f == 74:
                pressed['A'] = True         # nav map
            elif f == 80:
                shot('navmap')
                pressed['B'] = True
            elif f == 86:
                pressed['B'] = True         # leave the computer
                state['paused'] = True
            return
        # nearest hostile, else the destination
        tgt = None
        best = 1 << 30
        for i in range(1, W.NSHIP):
            ob = w.o[i]
            if ob.cls >= W.C_SHIP and ob.side == W.SIDE_KILRATHI and \
                    ob.special != W.SM_DYING:
                d = w.dist(p, ob)
                if d < best:
                    best = d
                    tgt = ob
        if tgt is None:
            if state['auto_wait'] > 0:
                state['auto_wait'] -= 1
            elif w.autopilot_ok() == 0 and w.dest < len(w.mis.objectives):
                x, y, z = w.objective_pos(w.dest)
                far = M.mag((x - p.x) >> 8, (y - p.y) >> 8,
                            (z - p.z) >> 8) > 9600
                if far:
                    # B + DOWN = autopilot (two frames: hold B, then tap)
                    pressed['B'] = True
                    if state['frame'] % 2:
                        pressed['DOWN'] = True
                        state['auto_wait'] = 12
                    return
            x, y, z = w.objective_pos(w.dest)
            rng = 99999
        else:
            x, y, z = tgt.x, tgt.y, tgt.z
            rng = best
        lx, ly, lz = M.to_frame(p.m, (x - p.x) >> 8, (y - p.y) >> 8,
                                (z - p.z) >> 8)
        yw, pt = M.spherical(lx, ly, lz)
        if yw > 2:
            pressed['RIGHT'] = True
        elif yw < -2:
            pressed['LEFT'] = True
        if pt > 2:                 # target below: push the stick forward
            pressed['UP'] = True
        elif pt < -2:
            pressed['DOWN'] = True
        if tgt is not None:
            if rng > 1200:
                pressed['RB'] = True
            elif rng < 500:
                pressed['LB'] = True
            if abs(yw) < 6 and abs(pt) < 6 and rng < 4500:
                pressed['A'] = True
        else:
            pressed['RB'] = True
        f = state['flight_frames']
        if f in (2, 40) or (tgt is not None and tgt.vis and rng < 1500 and
                            f - state['last_shot'] > 150):
            state['last_shot'] = f
            shot('flight')

    def step():
        tb._previous_keys = tb._current_keys.copy()
        pressed = {b: False for b in BTN}
        state['frame'] += 1
        n = state['frame']
        if n > args.max_frames:
            raise RuntimeError('frame budget exhausted in phase %s'
                               % state['phase'])
        ph = state['phase']
        if ph == 'menus':
            # title, main menu, carrier menu, briefing, launch: all "A"
            if n % 6 == 0:
                pressed['A'] = True
            if n in (3, 20, 40, 70, 100, 130) or (60 < n < 400 and
                                                  n % 60 == 5):
                shot('menu')
        elif ph == 'flight':
            fl = state['flight']
            if fl.w.result != 0:
                # shot down: back through the menus for another try
                state['phase'] = 'debrief' if fl.w.result == W.R_LANDED \
                    else 'menus'
                state['log'].append(('result', fl.w.result, fl.w.kills,
                                     fl.w.wing_kills, fl.w.tick))
                print('[selfplay] flight over: result %d, kills %d + %d, '
                      '%d turns' % (fl.w.result, fl.w.kills,
                                    fl.w.wing_kills, fl.w.tick))
                state['mark'] = n
                state['want_saves'] = state['saves'] + 1
            else:
                fly(pressed)
        elif ph == 'debrief':
            if state['saves'] >= state['want_saves']:
                state['phase'] = 'leave'
                state['mark'] = n
            else:
                if n % 6 == 0:
                    pressed['A'] = True
                if (n - state['mark']) % 45 == 20:
                    shot('debrief')
        elif ph == 'leave':
            k = n - state['mark']
            if k == 6:
                shot('carrier')
                pressed['B'] = True        # carrier menu: back = save+exit
            elif k == 20:
                pressed['UP'] = True       # main menu: wrap to "Exit"
            elif k == 30:
                shot('mainmenu')
                pressed['A'] = True
        tb._current_keys = pressed

    eng.update_button_state = step

    code = 0
    try:
        import main  # noqa: F401  (runs the game)
    except SystemExit:
        pass
    except BaseException as e:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        print('[selfplay] FAILED:', type(e).__name__, e)
        code = 1
    if code == 0:
        try:
            with open(save_path) as f:
                saved = json.load(f)
            ok = saved.get('missions') == 1 and state['log'] and \
                state['log'][-1][1] == W.R_LANDED
            print('[selfplay] save:', {k: saved[k] for k in (
                'series', 'mission', 'missions', 'kills', 'series_score')})
            if not ok:
                print('[selfplay] FAILED: mission was not completed')
                code = 1
        except (OSError, ValueError) as e:
            print('[selfplay] FAILED: no saved game (%s)' % e)
            code = 1
    if not args.keep_save:
        if os.path.exists(save_path):
            os.remove(save_path)
        if backup is not None:
            with open(save_path, 'w') as f:
                f.write(backup)
    print('[selfplay] %s after %d frames, %d screenshots in %s'
          % ('PASSED' if code == 0 else 'FAILED', state['frame'],
             state['shots'], OUT_DIR))
    sys.exit(code)


if __name__ == '__main__':
    main()
