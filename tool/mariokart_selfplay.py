#!/usr/bin/env python3
"""
mariokart_selfplay.py - headless scripted self-play test for the
MarioKarts game (PC target - a CPython/pygame emulation of the
ThumbyColor firmware).

Boots the game exactly like tool/run_pc.py does (SDL dummy drivers,
thumby_engine.pc.bootstrap, FPS calibration), then:

  * replaces the PC input polling (engine.tick ->
    thumbyButton.update_button_state) with a scene-aware driver;
  * wraps the game's scene functions (title / select_kart / race /
    result / _race_draw / SettingsMenu.run) so the driver knows
    exactly which scene is on screen (installed lazily on the first
    frame after the game module has finished importing);
  * drives the player kart with real button presses - throttle,
    look-ahead steering against the course tangent, corner braking
    and item use - pressing the physical buttons behind the game's
    live keymap, so it keeps working after a key remap;
  * plays a full session:

      title -> select (aim right once, pick kart 2)
      -> first-race HOW TO RACE overlay (dismiss)
      -> full 3-lap race -> results -> REMATCH
      -> 2nd race: early forfeit -> DNF results -> title
      -> settings: remap the first key row (capture with LB), run
         RESET DEFAULTS, save on the BACK row
      -> settings again: VIBRATION off, VOLUME up, QUIT -> reset()
         -> clean exit (code 0)

Pixel probes on the RGB565 framebuffer cross-check that each scene
actually paints (the screen is not blank, the select highlight box
and the settings divider are there, the results checker strip is
there, the race world is not blank).

Success = the scripted QUIT makes the game call reset(), which exits
the process with code 0. The run mutates keymap.json and creates
settings.json and .pc_wrapper_settings.json; their content is
printed and the state is restored to the pre-run state afterwards
(use -k to keep the mutations).

Usage:
    python3 tool/mariokart_selfplay.py
    python3 tool/mariokart_selfplay.py -k   # keep runtime state
"""

import os
import sys
import time
from math import atan2, pi

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = os.path.join(REPO, 'games', 'mariokart')
if not os.path.isdir(GAME_DIR):
    sys.exit(f'selfplay: unknown game directory: {GAME_DIR}')

KEEP = False
for a in sys.argv[1:]:
    if a == '-k':
        KEEP = True

# Headless SDL + silent audio (same as run_pc --headless). Must be
# set before pygame is imported anywhere.
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

sys.path.insert(0, REPO)
from thumby_engine.pc import bootstrap

print(f'[selfplay] booting game: mariokart', flush=True)
bootstrap(local_root=GAME_DIR)
sys.path.insert(0, GAME_DIR)

from thumby_engine.pc import fps_calibration
try:
    fps_calibration.get_fps_correction()
except Exception as e:
    print('[selfplay] FPS calibration skipped:', e)

import thumby_engine.pc.thumbyButton as tb
from thumby_engine.platform import display

# The game's engine module: tick() calls this module-global name, so
# patching the object's attribute is what scripts the inputs.
eng = sys.modules['engine']

# --- Framebuffer probes (RGB565, little endian) ----------------------------
FB = display.buffer
BG = 0x0008
DIM = 0x94EA
SEL = 0xFFE0
CHECK_A = 0xFFFF
CHECK_B = 0x1060
# World palette of the HTML-reference optics (mirrors constants.py)
GRASS = 0x6629
GRASS_B = 0x55C7
ROAD = 0x6B8F
ROAD_B = 0x634E
RUMBLE_A = 0xE1E7
RUMBLE_B = 0xF7BE
LANE = 0xEF5B
LINE = 0xFFFF


def px(x, y):
    i = (y * 128 + x) * 2
    return FB[i] | (FB[i + 1] << 8)


def nonbg_sampled(step=4):
    """Rough 'is the screen blank' count over a quarter-pixel grid."""
    n = 0
    for y in range(0, 128, step):
        base = y * 128 * 2
        for x in range(0, 128, step):
            i = base + x * 2
            c = FB[i] | (FB[i + 1] << 8)
            if c != BG:
                n += 1
    return n


# Keymap values are button object NAMES (get_pressed_key returns
# 'A','B','U','D','L','R','LB','RB','MENU' on every target), but the
# firmware key dict is indexed by each button's own ID, which differs
# between targets: the original Thumby uses 'U'/'D'/'L'/'R' while
# ThumbyColor/PC uses 'UP'/'DOWN'/'LEFT'/'RIGHT'. Map name -> id via
# the platform's button objects so presses land on the right key.
import thumby_engine.platform as _plat
NAME2ID = {
    'A': _plat.buttonA.button_id,
    'B': _plat.buttonB.button_id,
    'U': _plat.buttonU.button_id,
    'D': _plat.buttonD.button_id,
    'L': _plat.buttonL.button_id,
    'R': _plat.buttonR.button_id,
    'LB': _plat.buttonLB.button_id,
    'RB': _plat.buttonRB.button_id,
    'MENU': _plat.buttonMENU.button_id,
}
BTN_IDS = tuple(NAME2ID.values())

# Forfeited ~1.5 s into the run phase of the 2nd race (the countdown
# ends at tick ~210; _race_step only reads buttons from RC_RUN on).
FORFEIT_AT = 300
STALL_LIMIT = 3000     # ticks without progress / scene change -> fail
TOTAL_LIMIT = 60000    # absolute tick budget -> fail

# The scripted session. (scene, at, action, hold, every, count, name)
# Single presses use count 0 and a 1-step hold (hold 2 = pressed on
# exactly one step = one justPressed window). Sweeps press `count`
# times, `every` ticks apart, starting at `at`.
EVENTS = [
    ('title', 60, 'OK', 2, 0, 0, 'title: RACE'),
    ('select', 30, 'RIGHT', 2, 0, 0, 'select: aim right (kart 2)'),
    ('select', 70, 'OK', 2, 0, 0, 'select: pick kart 2'),
    ('help', 30, 'OK', 2, 0, 0, 'help: dismiss HOW TO RACE'),
    ('result', 60, 'OK', 2, 0, 0, 'result: REMATCH'),
    ('result', 60, 'BACK', 2, 0, 0, 'result 2: back to title'),
    ('title', 60, 'BACK', 2, 0, 0, 'title: SETTINGS'),
    ('settings', 30, 'OK', 2, 0, 0, 'settings: remap first key row'),
    ('settings', 80, 'LB', 2, 0, 0, 'settings: capture new key (LB)'),
    ('settings', 140, 'DOWN', 2, 12, 8, 'settings: down to RESET DEFAULTS'),
    ('settings', 300, 'OK', 2, 0, 0, 'settings: run RESET DEFAULTS'),
    ('settings', 340, 'DOWN', 2, 12, 2, 'settings: down to BACK row'),
    ('settings', 430, 'OK', 2, 0, 0, 'settings: BACK row (save + exit)'),
    ('title', 60, 'BACK', 2, 0, 0, 'title: SETTINGS (2nd)'),
    ('settings', 30, 'DOWN', 2, 12, 6, 'settings: down to VIBRATION'),
    ('settings', 140, 'OK', 2, 0, 0, 'settings: toggle VIBRATION'),
    ('settings', 180, 'DOWN', 2, 0, 0, 'settings: down to VOLUME'),
    ('settings', 220, 'OK', 2, 0, 0, 'settings: cycle VOLUME'),
    ('settings', 260, 'DOWN', 2, 12, 2, 'settings: down to QUIT'),
    ('settings', 360, 'OK', 2, 0, 0, 'settings: QUIT -> reset()'),
]


class Driver:
    def __init__(self):
        self.mg = None
        self.wrapped = False
        self.scene = None       # effective scene (incl. 'help')
        self.pending_check = None
        self.tick = 0           # frames in the current scene
        self.total = 0
        self.last_activity = 0
        self.last_act = None    # coarse race progress
        self.last_sel = None    # settings selection
        self.press = None       # (physical button, remaining steps)
        self.ei = 0
        self.sweep = None
        self.sweep_left = 0
        self.sweep_next = 0
        self.fires = []
        self.v = None           # latest race state (from _race_draw)
        self.menu = None        # latest SettingsMenu instance
        self.race_no = 0
        self.race_done = 0
        self.forfeit_at = 0
        self.aimed = False
        self.aim_checked = False
        self.race_world_checked = False
        self.checks = 0

    # -- scene wrappers ------------------------------------------------------
    def install_wrappers(self):
        mg = sys.modules['MainGame']
        self.mg = mg
        if self.wrapped:
            return
        self.wrapped = True
        orig_title = mg.title
        orig_select = mg.select_kart
        orig_race = mg.race
        orig_result = mg.result
        orig_draw = mg._race_draw
        orig_run = mg.SettingsMenu.run

        def title_probe():
            self.set_scene('title')
            return orig_title()

        def select_probe():
            self.set_scene('select')
            return orig_select()

        def race_probe(pick):
            self.race_no += 1
            n = self.race_no
            self.set_scene('race')
            res = orig_race(pick)
            self.race_done += 1
            standings, ppos, forfeit = res
            if n == 1:
                if forfeit:
                    raise RuntimeError('race 1: player forfeited '
                                       '(script should not press B)')
                you = [r for r in standings if '(YOU)' in r[1]]
                print(f'[selfplay] race 1 done: player P{ppos}, '
                      f'you row: {you[0] if you else "?"}', flush=True)
            else:
                if not forfeit:
                    raise RuntimeError(f'race {n}: expected a forfeit, '
                                       f'got a finish')
                you = [r for r in standings if '(YOU)' in r[1]]
                print(f'[selfplay] race {n} done: forfeit, '
                      f'you row: {you[0] if you else "?"}', flush=True)
            return res

        def result_probe(standings, pos, forfeit):
            self.set_scene('result')
            return orig_result(standings, pos, forfeit)

        def draw_probe(v, *args, **kw):
            self.v = v
            return orig_draw(v, *args, **kw)

        def run_probe(menu):
            self.menu = menu
            self.set_scene('settings')
            try:
                return orig_run(menu)
            finally:
                self.menu = None

        mg.title = title_probe
        mg.select_kart = select_probe
        mg.race = race_probe
        mg.result = result_probe
        mg._race_draw = draw_probe
        mg.SettingsMenu.run = run_probe
        print('[selfplay] scene wrappers installed', flush=True)

    def effective(self):
        # The first-race help overlay lives inside race()
        if (self.scene == 'race' and self.mg is not None
                and getattr(self.mg, 'first_race', False)):
            return 'help'
        return self.scene

    def set_scene(self, sc):
        if sc == self.scene:
            return
        tag = self.scene if self.scene is not None else 'boot'
        print(f'[selfplay] scene: {tag} -> {sc} '
              f'(frame {self.total})', flush=True)
        self.scene = sc
        self.tick = 0
        self.sweep = None
        self.press = None
        self.pending_check = sc
        if sc == 'race':
            self.v = None
            self.race_world_checked = False
            if self.race_no >= 2:
                self.forfeit_at = FORFEIT_AT
        elif sc == 'select':
            self.aimed = False
            self.aim_checked = False
        elif sc == 'settings':
            self.last_sel = None

    # -- physical button behind a logical action (keymap aware) --------------
    def phys(self, action):
        # The action's keymap value is a button NAME; the key dict is
        # indexed by the button's firmware ID (see NAME2ID).
        if action == 'LB':
            name = 'LB'
        else:
            mg = self.mg
            if mg is None:
                name = {'OK': 'A', 'BACK': 'B', 'LEFT': 'L', 'RIGHT': 'R',
                        'UP': 'U', 'DOWN': 'D'}[action]
            else:
                idx = {'LEFT': mg.KEY_LEFT, 'RIGHT': mg.KEY_RIGHT,
                       'UP': mg.KEY_UP, 'DOWN': mg.KEY_DOWN,
                       'OK': mg.KEY_OK, 'BACK': mg.KEY_BACK}[action]
                k = mg.KEYMAPS[idx]
                name = k if isinstance(k, str) else str(k)
        return NAME2ID[name]

    # -- race driving (look-ahead line against the course tangent) ----------
    def drive(self, pressed):
        mg = self.mg
        v = self.v
        if v['state'] != mg.RC_RUN:
            return  # countdown / finish coast: the game reads no input
        k = v['karts'][0]
        if k['stuck'] > 0:
            return  # stunned: let it recover without input
        if self.forfeit_at and self.tick >= self.forfeit_at:
            # one-shot drop-out press; the game reads justPressed
            self.forfeit_at = 0
            pressed[self.phys('BACK')] = True
            self.fires.append((self.total, 'race: FORFEIT (drop out)'))
            self.last_activity = self.total
            print(f'[selfplay] fire: race: FORFEIT (drop out) '
                  f'(frame {self.total})', flush=True)
            return
        sp = k['s'] >> 16
        # Aim at a point on the centerline ahead (a short look-ahead
        # when off the road, so the slow crawl leads back to it) and
        # steer until the course tangent matches that direction.
        look = 8 if k['off'] else (20 + sp * 2) // 3
        tp = (k['prog'] + look * 8) % mg.PC.L8
        tx, ty = mg._tp8(tp, 0)
        dx = tx - (k['x'] >> 13)
        dy = ty - (k['y'] >> 13)
        des = int(atan2(dy, dx) * 1024 / (2 * pi)) & 1023
        s = mg._sub_of_prog8(k['prog'])
        diff = ((des - mg.PC.SANG[s] + 512) & 1023) - 512
        pressed[self.phys('UP')] = True
        th = 30 if k['off'] else 48
        if diff > th:
            pressed[self.phys('RIGHT')] = True
        elif diff < -th:
            pressed[self.phys('LEFT')] = True
        if (not k['off'] and k['s'] > (k['sm'] * 3) // 4
                and abs(diff) > 160):
            pressed[self.phys('DOWN')] = True  # brake hard corners
        if k['item'] >= 0:
            pressed[self.phys('OK')] = True  # use the item at once

    # -- per-scene pixel sanity checks ---------------------------------------
    def do_check(self, sc):
        if sc == 'title' or sc == 'help':
            # The title is the live attract race (sky, road, karts)
            # plus the panel; the help overlay is text on BG. Both
            # leave hundreds of non-bg samples on a quarter-pixel
            # grid; a blank screen is 0, text only is ~35-100.
            n = nonbg_sampled()
            if n < 60:
                raise RuntimeError(f'{sc} screen nearly blank ({n} '
                                   f'non-bg samples)')
        elif sc == 'select':
            # The highlight box (col*31, 14) 33x28 is a 1px outline.
            # Probe a side-edge pixel, not the top row: the top row
            # (y=14) is shared with the neighbouring box's corner and
            # with the header text, so it cannot discriminate.
            # c=0: left edge x=0; c=1: right edge x=63 (kart sprites
            # span col*31+2 .. col*31+31, so x=63 is covered only by
            # the col-1 outline).
            x = 63 if self.aimed else 0
            c = px(x, 20)
            if c != SEL:
                raise RuntimeError(f'select highlight missing at '
                                   f'({x},20) = {c:#06x}')
        elif sc == 'race':
            if not self.race_world_checked:
                p = self.v['karts'][0] if self.v else None
                if p is None:
                    return False  # retry once the race state exists
                if not p['off']:
                    # Camera sanity: the player kart is drawn at the
                    # view anchor (row ~105 on color) and the road
                    # must run ahead of it toward the horizon.
                    anchor = 0
                    for y in range(84, 106):
                        for x in range(50, 78):
                            c = px(x, y)
                            if c not in (GRASS, GRASS_B, ROAD, ROAD_B,
                                         RUMBLE_A, RUMBLE_B, LANE,
                                         CHECK_A, CHECK_B, SEL):
                                anchor += 1
                    if anchor < 40:
                        raise RuntimeError(f'race: no player kart '
                                           f'at view anchor '
                                           f'({anchor} non-road px)')
                    # The road's screen position depends on the course
                    # geometry: on the spawn curve it hugs the right
                    # edge (rows 60-95) with the wide run below, on
                    # straights it is centred - so gate on the whole
                    # ground region instead of one fixed box. A good
                    # frame has thousands of road-family pixels (base
                    # colors plus their FOG50 sky blends) and only a
                    # few legitimate dark sprite pixels; the historical
                    # failures were a black band (thousands of 0x0000)
                    # or a missing/garbled road.
                    # road family = the reference-optics palette plus
                    # every haze level of its fog blend tables (the
                    # game builds those from PC, so read them live)
                    roadset = {ROAD, ROAD_B, RUMBLE_A, RUMBLE_B, LANE,
                               CHECK_A, CHECK_B}
                    if self.mg is not None:
                        for name in ('FOGT_ROAD_A', 'FOGT_ROAD_B',
                                     'FOGT_RUMBLE_A', 'FOGT_RUMBLE_B',
                                     'FOGT_LANE', 'FOGT_CHECK_A',
                                     'FOGT_CHECK_B'):
                            roadset.update(getattr(self.mg.PC,
                                                   name, ()))
                    road = 0
                    black = 0
                    for y in range(40, 128):
                        for x in range(128):
                            c = px(x, y)
                            if c == 0:
                                black += 1
                            elif c in roadset:
                                road += 1
                    if black > 64:
                        raise RuntimeError(f'race: {black} black px '
                                           f'below the horizon')
                    if road < 1500:
                        raise RuntimeError(f'race: not enough road '
                                           f'({road} road px, want '
                                           f'>= 1500)')
                self.race_world_checked = True
        elif sc == 'result':
            a, b = px(4, 120), px(12, 120)
            if (a not in (CHECK_A, CHECK_B)
                    or b not in (CHECK_A, CHECK_B)):
                raise RuntimeError(f'results checker strip missing '
                                   f'({a:#06x}, {b:#06x})')
        elif sc == 'settings':
            c = px(0, 14)
            if c != DIM:
                raise RuntimeError(f'settings divider missing '
                                   f'(px(0,14) = {c:#06x})')
        self.checks += 1
        return True

    # -- per-frame input driver (replaces thumbyButton.update_button_state) --
    def step(self):
        tb._previous_keys = tb._current_keys.copy()
        pressed = {b: False for b in BTN_IDS}

        mg = sys.modules.get('MainGame')
        if mg is not None and hasattr(mg, 'main') and not self.wrapped:
            self.install_wrappers()
        if (self.scene is None and mg is not None
                and hasattr(mg, 'main')):
            # The module just finished importing: the first screen up
            # is the title (main() calls it right away).
            self.set_scene('title')

        eff = self.effective()
        if eff != self.scene:
            self.set_scene(eff)
        # The help overlay ends inside the already-running race() - no
        # scene entry fires. When the game clears first_race, the
        # countdown starts at once: back to the 'race' scene.
        if (self.scene == 'help' and self.mg is not None
                and not self.mg.first_race):
            self.set_scene('race')
        self.tick += 1
        self.total += 1

        if self.scene is not None:
            if self.pending_check is not None:
                if self.do_check(self.pending_check):
                    self.pending_check = None
            if (self.scene == 'select' and self.aimed
                    and not self.aim_checked):
                c = px(63, 20)
                if c != SEL:
                    raise RuntimeError(f'select aim did not move the '
                                       f'highlight (px(63,20) = {c:#06x})')
                self.aim_checked = True

            # -- activity / timeouts
            if self.scene == 'race' and self.v is not None:
                act = self.v['karts'][0]['total'] // 8
                if act != self.last_act:
                    self.last_act = act
                    self.last_activity = self.total
            elif self.scene == 'settings' and self.menu is not None:
                if self.menu.selected != self.last_sel:
                    self.last_sel = self.menu.selected
                    self.last_activity = self.total
            if self.total - self.last_activity > STALL_LIMIT:
                nxt = (EVENTS[self.ei][6] if self.ei < len(EVENTS)
                       else '(script done)')
                raise TimeoutError(
                    f'stalled at frame {self.total}: scene {self.scene} '
                    f'local {self.tick}, waiting for: {nxt}')
            if self.total > TOTAL_LIMIT:
                raise TimeoutError(
                    f'absolute tick budget {TOTAL_LIMIT} exceeded '
                    f'(scene {self.scene})')

            # -- continuous race driving
            if self.scene == 'race' and self.v is not None:
                self.drive(pressed)

            # -- linear event script
            if (self.sweep is None and self.ei < len(EVENTS)
                    and self.press is None):
                e = EVENTS[self.ei]
                if e[0] == self.scene and self.tick >= e[1]:
                    if e[5]:  # sweep
                        self.sweep = e
                        self.sweep_left = e[5] - 1  # this press is #1
                        self.sweep_next = self.tick + e[4]
                    else:
                        self.ei += 1
                    self.press = (self.phys(e[2]), e[3])
                    self.fires.append((self.total, e[6]))
                    self.last_activity = self.total
                    if e[6].startswith('select: aim'):
                        self.aimed = True
                    print(f'[selfplay] fire: {e[6]} (scene {self.scene} '
                          f'local {self.tick} frame {self.total})',
                          flush=True)
            elif self.sweep is not None and self.press is None:
                if (self.scene == self.sweep[0]
                        and self.tick >= self.sweep_next):
                    self.press = (self.phys(self.sweep[2]),
                                  self.sweep[3])
                    self.sweep_left -= 1
                    self.sweep_next += self.sweep[4]
                    n = self.sweep[5] - self.sweep_left
                    self.fires.append(
                        (self.total,
                         f'{self.sweep[6]} ({n}/{self.sweep[5]})'))
                    self.last_activity = self.total
                    print(f'[selfplay] sweep: {self.fires[-1][1]} '
                          f'(frame {self.total})', flush=True)
                    if self.sweep_left == 0:
                        self.sweep = None
                        self.ei += 1

            # -- hold / release the active press
            if self.press is not None:
                btn, rem = self.press
                if rem <= 1:
                    self.press = None
                else:
                    pressed[btn] = True
                    self.press = (btn, rem - 1)

        tb._current_keys = pressed


driver = Driver()
eng.update_button_state = driver.step

# Snapshot runtime state files so the run can be made non-destructive.
SNAP_FILES = ('keymap.json', 'settings.json',
              '.pc_wrapper_settings.json')
snapshots = {}
for name in SNAP_FILES:
    p = os.path.join(GAME_DIR, name)
    if os.path.exists(p):
        with open(p, 'rb') as f:
            snapshots[name] = f.read()
    else:
        snapshots[name] = None

# Deterministic verification: pin the RNG so runs are comparable -
# item spawns (randint(1,100)) and AI jitter make race outcomes
# luck-dependent without this.
import random
_sd = os.environ.get('SELFPLAY_SEED')
if _sd is not None:
    random.seed(_sd)

t0 = time.time()
print(f'[selfplay] running script ({len(EVENTS)} events)...', flush=True)
rc = 'fail'
try:
    import main  # runs the game; ends via reset() -> sys.exit(0)
    print('[selfplay] game import returned without exiting')
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else 0
    rc = 'pass' if code == 0 else 'fail'
    print(f'[selfplay] game exited: code {code}', flush=True)
except TimeoutError as e:
    print(f'[selfplay] TIMEOUT: {e}', flush=True)
except BaseException as e:
    import traceback
    traceback.print_exc()
    print(f'[selfplay] game crashed: {type(e).__name__}: {e}', flush=True)
finally:
    print(f'[selfplay] total frames: {driver.total}, '
          f'wall time: {time.time() - t0:.1f}s, '
          f'races: {driver.race_done}, '
          f'events fired: {len(driver.fires)}, '
          f'scene checks: {driver.checks}', flush=True)
    for frame, name in driver.fires:
        print(f'  frame {frame:6d}: {name}')
    for name in SNAP_FILES:
        p = os.path.join(GAME_DIR, name)
        if os.path.exists(p):
            with open(p, 'r') as f:
                print(f'[selfplay] {name}: {f.read()}')
    if not KEEP:
        for name, data in snapshots.items():
            p = os.path.join(GAME_DIR, name)
            if data is not None:
                with open(p, 'wb') as f:
                    f.write(data)
            elif os.path.exists(p):
                os.remove(p)
        print('[selfplay] runtime state restored')

print(f'[selfplay] RESULT: {rc.upper()}', flush=True)
sys.exit(0 if rc == 'pass' else 1)
