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
tool/wc1_convert.py). It also watches the talking heads during the
briefing and plays one scripted "Meanwhile..." cutscene after the
run, asserting both pictures are not black (docs/05 5.7, docs/06
6.1). The hard scenes of docs/06 6.2 are checked the same way: the
hangar, deck, launch door, fly-off and landing a sortie shows are
watched while they play, and death, ejection and stranded - which a
landing run never reaches - are played afterwards. Every scene that
really plays must paint a picture and be photographed. Screenshots
of the stages are written to build/wc1_selfplay/ so the pictures can
be checked by eye. The opening cinematic (docs/06 6.2, title.c's
Title_Sequence) plays in full: the pilot is held off while it runs,
and its stages - opening text, logo zoom, credits, close and menu -
are photographed in turn.

The Origin FX startup intro (docs/06 6.2, dos_intro.c's
SdlPlayDosStartupIntro) - the orchestra, the Earth behind it, the
ORION logo zoom and the fireworks - plays before the title and is
photographed as well.

Usage:
    python3 tool/wc1_selfplay.py            # first mission
    python3 tool/wc1_selfplay.py --seed 7 --max-frames 9000
"""

import argparse
import faulthandler
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
    # If the harness ever spins without progressing, this watchdog writes
    # the live Python stack to stderr every 25 seconds (unbuffered, so it
    # shows even while stdout is block-buffered) - the fastest way to find
    # a blocking screen that never lets the pilot run.
    faulthandler.dump_traceback_later(25, repeat=True)
    # Import PIL before bootstrap(): the PC emulation replaces the
    # real thread module with a stub, and PIL (via warnings on
    # Python 3.14) needs the genuine one. Loading it here means the
    # lazy "from PIL import Image" in shot() never re-executes it.
    try:
        import PIL                          # noqa: F401
        from PIL import Image               # noqa: F401
        # Image.save() pulls in PngImagePlugin lazily, which imports
        # logging, which needs the real time module - all of that has
        # to happen before bootstrap() installs the stubs.
        from PIL import PngImagePlugin      # noqa: F401
        import logging                      # noqa: F401
    except ImportError:
        pass
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
    flight.PACE = False                    # a game turn every frame
    import campaign
    import wcmath as M
    import world as W
    import scramble, launchseq, deathseq, ejectseq   # docs/06 6.2
    import funeralseq
    import titleseq
    import introfx

    state = {'frame': 0, 'flight': None, 'saves': 0, 'shots': 0,
             'phase': 'menus', 'done_at': None, 'flight_frames': 0,
             'last_shot': -999, 'auto_wait': 0, 'log': [], 'upd': 0,
             'tshots': {}}

    def picture_nonblack():
        """Visible pixels in the conversation picture rows 16..77 -
        close_talk's viewport (talk.py:482-543)."""
        b = bytes(plat.display.buffer)
        n = 0
        for row in range(16, 78):
            base = row * 256
            for i in range(base, base + 256, 2):
                if b[i] | b[i + 1] << 8:
                    n += 1
        return n

    def picture_text():
        """Visible pixels in the subtitle rows 79..111 (scene.py:79-81,
        TXT_Y = 79; the status bar starts at row 112)."""
        b = bytes(plat.display.buffer)
        n = 0
        for row in range(79, 112):
            base = row * 256
            for i in range(base, base + 256, 2):
                if b[i] | b[i + 1] << 8:
                    n += 1
        return n

    def picture_full():
        """Visible pixels in the whole space-buffer picture, rows
        16..111: the hard scenes fill every row and clip at row 112
        (launchseq.py:48), unlike the conversation band above."""
        b = bytes(plat.display.buffer)
        n = 0
        for row in range(16, 112):
            base = row * 256
            for i in range(base, base + 256, 2):
                if b[i] | b[i + 1] << 8:
                    n += 1
        return n

    # the smallest picture that counts as painted; the stranded scene
    # is text on black, so it is held to a lower bar
    SCENE_MIN = {'stranded': 30}

    # the opening cinematic is photographed stage by stage; titleseq.stage
    # names the one playing ('A'..'E', 'menu'; every stage has its own
    # shot now - the fly-by in 'B' is the part the user asked to see)
    STAGE_SHOT = {'A': 'titleA', 'B': 'titleB', 'C': 'titleC',
                  'D': 'titleD', 'E': 'titleE', 'menu': 'titlemenu'}

    import talk

    real_load_face = talk.Talk.load_face

    def load_face(self, face):
        """Watch the talking heads (docs/05 5.7): remember the face
        when it really loaded, so step() can check the picture."""
        r = real_load_face(self, face)
        if self.head is not None:
            state['head_pending'] = face
            state['heads'] = state.get('heads', []) + [face]
            state['head_px'] = state.get('head_px', [])
        return r
    talk.Talk.load_face = load_face

    real_init = flight.Flight.__init__

    def init(self, *a, **k):
        real_init(self, *a, **k)
        state['flight'] = self
        state['phase'] = 'flight'
        # flight.Flight(self.T, ai, fonts, pal, st, ...) - MainGame.py
        # 401-404: keep the campaign state and the tables for the
        # post-run cutscene check
        state['ai'] = a[1]
        state['st'] = a[4]
        print('[selfplay] flight started at frame', state['frame'])
    flight.Flight.__init__ = init

    # The game lets the flight code go for the title and re-imports
    # it when it launches (docs/12 12.2). A re-imported flight is a
    # fresh module, not the one wrapped above, and fly() builds its
    # Flight right after the import, before the pump could re-wrap it
    # in step(). So patch every flight module on its way through
    # __import__.
    import builtins
    real_import = builtins.__import__

    def patched_import(name, *a, **k):
        m = real_import(name, *a, **k)
        if name == 'flight' and m.Flight.__init__ is not init:
            m.PACE = False               # a game turn every frame
            m.Flight.__init__ = init
        # The same fresh-module story as flight above: the title pops
        # the scene modules and the mission re-imports them, so a game
        # call lands on a fresh function the setup wraps never touched.
        # Re-apply the wrapper on every import of a listed name and the
        # call counts, the spent press and the scene marker keep
        # working across the reloads (docs/12 12.2).
        for attr in SCENE_BY_NAME.get(name, ()):
            fn = getattr(m, attr, None)
            if fn is not None and not getattr(fn, '_selfplay_wrap',
                                              False):
                wrap(m, attr)
        return m
    builtins.__import__ = patched_import

    real_save = campaign.State.save

    def save(self):
        state['saves'] += 1
        return real_save(self)
    campaign.State.save = save

    # docs/06 6.2: the hard scenes. Game.mission calls them around the
    # flight; wrapping the entry points counts the calls and lets a
    # scene play to its end. Two things would cut a scene short and
    # hide its picture: the press that picked the menu item is still
    # "just pressed" when the scene starts (thumbyButton.py:148-151),
    # and the deadlock pump below would fire its rescue B as soon as
    # the scene's busy-wait pumped the display 300 times. The wrapper
    # spends the press, marks the running scene, and the pump holds
    # its breaker while state['scene'] names one.
    state['scene'] = None
    state['scenes'] = {}        # name -> [calls, picture px, text px,
                                #              shot taken, ship arg]
    SHIP_ARG = {'deck': 0, 'door': 0, 'flyoff': 0, 'death': 0,
                'eject': 0, 'landing': 1}    # landing(damage, ship)

    def wrap(mod, attr):
        real = getattr(mod, attr)

        def f(*a, **k):
            rec = state['scenes'].setdefault(
                attr, [0, 0, 0, False, None])
            rec[0] += 1
            i = SHIP_ARG.get(attr)
            if i is not None and len(a) > i:
                rec[4] = a[i]
            state['scene'] = attr
            tb._current_keys = {}     # the press that led here is spent
            tb._previous_keys = {}
            print('[selfplay] %s starts at frame %d'
                  % (attr, state['frame']))
            try:
                return real(*a, **k)
            finally:
                state['scene'] = None
        f._selfplay_wrap = True     # marks a wrapped entry point for
                                    # the import hook below
        setattr(mod, attr, f)

    SCENE_BY_NAME = {}
    for _m, _a in ((scramble, 'hangar'), (scramble, 'deck'),
                   (scramble, 'landing'), (launchseq, 'door'),
                   (launchseq, 'flyoff'), (deathseq, 'death'),
                   (ejectseq, 'eject'), (ejectseq, 'stranded'),
                   (funeralseq, 'funeral'), (titleseq, 'title'),
                   (introfx, 'play')):
        wrap(_m, _a)
        SCENE_BY_NAME.setdefault(_m.__name__, []).append(_a)

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
        # MainGame's title releases the flight code and brings it
        # back lazily when a flight starts (docs/12 12.2): a fresh
        # flight module has a Flight.__init__ that is not the capture
        # wrapper and a PACE back to the real pacing. Put both
        # patches back before a flight can be built - which happens
        # after the carrier menu, where the pilot runs.
        fm = sys.modules.get('flight')
        if fm is not None and fm.Flight.__init__ is not init:
            fm.PACE = False                # a game turn every frame
            fm.Flight.__init__ = init
        # docs/06 6.2: the title cinematic is a hard scene too, but its
        # own menu is the one part the pilot has to drive (titleseq.hold
        # goes False when the cinematic ends) - without that the run
        # would sit in the menu forever with the breaker held off as
        # long as a scene is named.
        if state['scene'] is not None and not (state['scene'] == 'title'
                                               and not titleseq.hold):
            # a hard scene is playing. color.py:205-209 runs an engine
            # tick inside every display.update(), and the scenes pump
            # the display by the thousands while they pace themselves -
            # so the pilot would otherwise run during the scene and its
            # presses would hit the scene's own button reads and cut it
            # short (docs/06 6.2). Hold the pilot out: no press, no
            # frame, keys stay spent.
            tb._current_keys = {}
            tb._previous_keys = {}
            return
        state['upd'] = 0              # the pilot ran: no deadlock
        tb._previous_keys = tb._current_keys.copy()
        pressed = {b: False for b in BTN}
        state['frame'] += 1
        n = state['frame']
        if n > args.max_frames:
            raise RuntimeError('frame budget exhausted in phase %s'
                               % state['phase'])
        if state.get('head_pending') is not None:
            # a talking head was just loaded and shown: screenshot it
            # and check the picture rows are not empty (docs/05 5.7)
            face = state['head_pending']
            state['head_pending'] = None
            shot('head%02d' % face)
            npx = picture_nonblack()
            state['head_px'].append(npx)
            print('[selfplay] head %d picture: %d pixels' % (face, npx))
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

    real_buttons = eng.update_button_state   # pc/engine.py's own reader
    eng.update_button_state = step

    # A screen that waits for a button press blocks the engine loop, so
    # the pilot (step) cannot run and no press ever arrives - the loop
    # then spins forever. Every screen pumps the display while it waits
    # (ui.py:113, 150, 169), so watching the pump spots the deadlock:
    # if it runs 300 times without a step, press B once. Every screen
    # reads B as back / skip, the block breaks and the pilot gets its
    # turn again. Flight is never affected: the pilot presses on every
    # frame, which resets the counter long before 300.
    base_update = plat.display.update        # the real blit

    def update_pump(*a):
        state['upd'] += 1
        sc = state['scene']
        if sc is not None:
            # a hard scene is playing: measure its picture, photograph
            # it once it is visibly painted, and hold the breaker off -
            # a scene cut short proves nothing (docs/06 6.2)
            rec = state['scenes'][sc]
            n = picture_full()
            if n > rec[1]:
                rec[1] = n
            t = picture_text()
            if t > rec[2]:
                rec[2] = t
            if n >= SCENE_MIN.get(sc, 100) and not rec[3]:
                rec[3] = True
                shot(sc)
            if sc == 'title':
                tag = STAGE_SHOT.get(titleseq.stage)
                if tag and not state['tshots'].get(tag) and (
                        tag != 'titleC' or titleseq.dist <= 30):
                    # the logo is photographed once it is big enough to
                    # read, not at the small start of the zoom
                    state['tshots'][tag] = True
                    shot(tag)
        elif state['upd'] > 300:
            state['upd'] = 0
            tb._current_keys['B'] = True
            tb._previous_keys['B'] = False
        base_update(*a)
    plat.display.update = update_pump

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
    if code == 0:
        heads = state.get('heads', [])
        if not heads:
            print('[selfplay] FAILED: no talking head was shown')
            code = 1
        elif state.get('head_px') and min(state['head_px']) < 100:
            print('[selfplay] FAILED: talking-head picture was black')
            code = 1
    # One scripted "Meanwhile..." cutscene, played the way the game
    # plays it (docs/06 6.1). A single sortie never leaves series 1,
    # so the hook above would never fire; play mid02 right after the
    # run and watch the picture through display.update instead.
    if code == 0 and state.get('st') is not None and \
            os.path.exists(os.path.join(GAME_DIR, 'assets',
                                        'mid02.wc')):
        state['mw_px'] = 0
        state['mw_tx'] = 0
        snap = [False]
        snap2 = [False]
        # watch the cutscene through the real blit, bypassing the
        # deadlock pump: a cutscene waiting for a key release must
        # never see a pulsed B, or it would break out unseen
        real_update = base_update

        def upd(*a):
            n = picture_nonblack()
            if n > state['mw_px']:
                state['mw_px'] = n
            if n >= 100 and not snap[0]:
                snap[0] = True
                shot('meanwhile')
            t = picture_text()
            if t > state['mw_tx']:
                state['mw_tx'] = t
            if t >= 300 and not snap2[0]:
                snap2[0] = True
                shot('meanwhile_text')
            return real_update(*a)
        # the frame counter must not run while the cutscene plays: the
        # display pump would call step() again and blow the budget.
        # The engine's own reader finds no pygame and leaves the keys
        # empty, so nothing is ever pressed and wait_release returns at
        # once (ui.py:32-38).
        eng.update_button_state = real_buttons
        tb._current_keys = {}
        tb._previous_keys = {}
        plat.display.update = upd
        try:
            import scene
            # variant 1, not the bare word: this one plays five
            # subtitle records (wc1_scene.py: "scene 2 v1: 5 records")
            # so the text director runs as well as the picture
            scene.show(2, 1, state['st'], state['ai'])
        finally:
            plat.display.update = real_update
        sys.modules.pop('scene', None)
        print('[selfplay] meanwhile picture: %d pixels, subtitle %d'
              % (state['mw_px'], state['mw_tx']))
        if state['mw_px'] < 100:
            print('[selfplay] FAILED: meanwhile picture was black')
            code = 1
        if state['mw_tx'] < 30:
            print('[selfplay] FAILED: meanwhile subtitles were black')
            code = 1
    # docs/06 6.2: the endings a landing run never plays. The flight
    # came back, so death, ejection and stranded never appeared in the
    # run; play them the way the game plays them (gameflow.c:372-375,
    # 401) and watch the pictures through the real blit. No engine
    # loop runs any more and no key is ever pressed, so every scene
    # plays to its end; the wrapper prints what each one paints.
    if code == 0 and state.get('st') is not None:
        ship = state['st'].ship
        if ship not in (0, 1, 2, 3):
            ship = 0
        eng.update_button_state = real_buttons
        tb._current_keys = {}
        tb._previous_keys = {}

        def upd_hard(*a):
            sc = state['scene']
            n = picture_full()
            t = picture_text()
            if sc is not None:
                rec = state['scenes'][sc]
                if n > rec[1]:
                    rec[1] = n
                if t > rec[2]:
                    rec[2] = t
                if n >= SCENE_MIN.get(sc, 100) and not rec[3]:
                    rec[3] = True
                    shot(sc)
            return base_update(*a)
        plat.display.update = upd_hard
        try:
            # the player's funeral follows the death (gameflow.c:401-407)
            for _m, _a, _args in ((deathseq, 'death', (ship,)),
                                  (funeralseq, 'funeral',
                                   (1, state['ai'], state['st'])),
                                  (ejectseq, 'eject', (ship,)),
                                  (ejectseq, 'stranded', ())):
                if _a in state['scenes']:
                    continue    # this run already showed that ending
                getattr(_m, _a)(*_args)
        finally:
            plat.display.update = base_update
    # docs/06 6.2 checks. A landed sortie must show the launch scenes
    # and the landing. Every scene that really plays must have painted
    # a picture and been photographed - a scene skipped because the
    # player ship is not one of the four WC1 cockpits (launchseq.py:128)
    # is allowed to paint nothing - and at the landing the deck crew
    # must have commented on the damage (scramble.py:711).
    if code == 0:
        seen = state['scenes']
        if state['log'] and state['log'][-1][1] == W.R_LANDED:
            expect = ('hangar', 'deck', 'door', 'flyoff', 'landing')
        else:
            expect = ('hangar', 'deck', 'door')
        for name in expect:
            if seen.get(name, [0])[0] < 1:
                print('[selfplay] FAILED: %s was never called' % name)
                code = 1
        if seen.get('title', [0])[0] < 1:
            print('[selfplay] FAILED: title was never called')
            code = 1
        if seen.get('play', [0])[0] < 1:
            print('[selfplay] FAILED: the intro was never played')
            code = 1
        for tag in ('titleA', 'titleB', 'titleC', 'titleD', 'titleE',
                    'titlemenu'):
            if not state['tshots'].get(tag):
                print('[selfplay] FAILED: no screenshot of %s' % tag)
                code = 1
        for name in seen:
            rec = seen[name]
            print('[selfplay] %s: %d calls, picture %d px, text %d px'
                  % (name, rec[0], rec[1], rec[2]))
            if name in SHIP_ARG and rec[4] not in (0, 1, 2, 3):
                continue        # not a WC1 cockpit: the scene skipped
            if rec[1] < SCENE_MIN.get(name, 100):
                print('[selfplay] FAILED: %s picture was black' % name)
                code = 1
            elif not rec[3]:
                print('[selfplay] FAILED: no screenshot of %s' % name)
                code = 1
        for name in ('death', 'funeral', 'eject', 'stranded'):
            if name not in seen:
                print('[selfplay] FAILED: %s did not play' % name)
                code = 1
        land = seen.get('landing')
        if land is not None and land[4] in (0, 1, 2, 3) and land[2] < 30:
            print('[selfplay] FAILED: the deck crew said nothing')
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
