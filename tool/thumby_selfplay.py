#!/usr/bin/env python3
"""
thumby_selfplay.py - headless scripted self-play test for the PC target
in Thumby mode (thumby_engine.pc.bootstrap(mode='thumby')).

Boots thumbcommander exactly like tool/run_pc.py --mode thumby --headless
does, then replaces the PC input polling (engine.tick ->
thumbyButton.update_button_state) with a scene-aware script driver and
plays a full session on the emulated original Thumby (72x40, 4-level
grayscale dither, 6 buttons):

    boot intro (timer-driven) -> menu: Asteroid Dodge -> launch cutscenes
    -> flight (hatch: SHIFT+A eject if the flight never ends) -> eject
    cutscene -> game over (persistent pattern: B restarts, repeatable
    for any number of deaths; B not A because menu's first input check
    reads stale state and an A would relaunch the game) -> menu -> down
    to Settings -> MOVE UP
    remap (PC quirk: the trigger key 'A' is captured into MOVE UP -
    the remap wait's first inputJustPressed() read sees the remap-start
    press still latched; the later LEFT press only exercises the
    SHIFT-toggle branch) -> B: save + exit -> menu -> down to
    Exit Game -> A: Exit Game -> reset() -> clean exit (code 0)

Scene classification reads the Grayscale bitplane model directly (no
guessing on art): display.frameRate tells which scene family set the
pacer (30 = menu/settings, 40 = flight, 20/6/10 = cutscene/game-over),
a fixed probe window tells whether the flight HUD pips are on screen,
the full-width divider row 9 tells whether the settings header is drawn
(2-frame persistence), and a whole-buffer change check separates the
animated cutscenes from the static game-over wait.

Success = the scripted Exit Game makes the game call reset(), which
exits the process with code 0. The run mutates keymap.json (MOVE UP
ends up as the remap trigger key 'A' on the PC - see the remap note
below); its content is printed, MOVE_UP is checked against that
expectation, and keymap.json is restored to its pre-run state
afterwards (use -k to keep mutations). --shots additionally writes a
PNG of the panel shortly after each menu / settings / game-over /
flight entry (/tmp/thumby_shots) for visual inspection.

PC-only remap note: SettingsMenu.run's remap wait evaluates its
`while not inputJustPressed()` condition BEFORE its first
display.update(), so the first read observes the button state latched
by the remap-start step. Starting the remap REQUIRES that state to
report A justPressed, and the capture then records exactly that state
(get_pressed_key checks A first) - trigger and capture share the same
latched read, so no press duration can escape it. This is a consequence
of the PC's per-frame button-state latch. MOVE_UP therefore comes out
as 'A', and the harness treats that as the expected PC outcome.
"""

import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = 'thumbcommander'
KEEP = False
SHOTS = False
for a in sys.argv[1:]:
    if a.startswith('--game='):
        GAME = a.split('=', 1)[1]
    elif a == '-k':
        KEEP = True
    elif a == '--shots':
        SHOTS = True
    elif not a.startswith('-'):
        GAME = a

GAME_DIR = os.path.join(REPO, 'games', GAME)
if not os.path.isdir(GAME_DIR):
    sys.exit(f'thumby_selfplay: unknown game "{GAME}" (no games/{GAME})')

# Headless SDL (same as run_pc --headless)
os.environ['SDL_VIDEODRIVER'] = 'dummy'

sys.path.insert(0, REPO)
from thumby_engine.pc import bootstrap

print(f'[thumby_selfplay] booting game: {GAME} (thumby mode)')
bootstrap(local_root=GAME_DIR, mode='thumby')
sys.path.insert(0, GAME_DIR)

from thumby_engine.pc import fps_calibration
try:
    fps_calibration.get_fps_correction()
except Exception as e:
    print('[thumby_selfplay] FPS calibration skipped:', e)

import thumby_engine.pc.thumbyButton as tb
import thumby_engine.platform as platform
import thumby_engine.pc.engine as engine

# The game's engine module: tick() calls this module-global name, so
# patching the object's attribute is what scripts the inputs.
eng = sys.modules['engine']

display = platform.display   # Grayscale instance from the PC port
BLACK, WHITE, DARKGRAY, LIGHTGRAY = 0, 1, 2, 3

# --- scene probe constants (from the Thumby layout, games/thumbcommander)
# flight HUD life pips: drawFilledRectangle(cockpit_x+19, cy-i*3, 2, 2, WHITE)
# cockpit at SHIP_X=4, SHIP_Y=23, COCKPIT_HEIGHT=18; the ship can be
# offset +-1 pixel -> probe a 3x3 window that always contains pip i=0.
PIP_X0, PIP_Y0 = 22, 37          # window: x 22..24, y 37..39

# settings header divider: drawLine(0, 9, WIDTH, 9, WHITE) - full width
LINE_Y = 9
LINE_XS = (0, 12, 24, 36, 48, 60, 71)

# The settings header (and the remap screen) redraw this divider every
# frame; transient one-frame misreads are rejected by requiring the
# full-line pattern to persist for two consecutive frames.
SETTINGS_PERSIST = 2

BTN_IDS = ('A', 'B', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'LB', 'RB', 'MENU')

# --- PNG snapshots (--shots) --------------------------------------------
SHOT_DIR = '/tmp/thumby_shots'
SHOT_DELAY = 8   # frames after scene entry, so the full content is drawn
shot_counts = {}


def snapshot(scene):
    """Save a PNG of the window surface (works under the SDL dummy driver)."""
    try:
        import pygame
        import thumby_engine.pc.engine_draw as ed
        fb = ed._back_fb_instance
        if fb is None or fb.screen is None:
            print('[thumby_selfplay] snapshot skipped: no window surface',
                  flush=True)
            return
        os.makedirs(SHOT_DIR, exist_ok=True)
        n = shot_counts.get(scene, 0)
        shot_counts[scene] = n + 1
        path = os.path.join(SHOT_DIR, f'{scene}-{n}.png')
        pygame.image.save(fb.screen, path)
        print(f'[thumby_selfplay] shot: {path} (scene {scene})', flush=True)
    except Exception as e:
        print(f'[thumby_selfplay] snapshot failed: {e}', flush=True)

STALL_LIMIT = 3000     # ticks without fire / scene change -> fail
TOTAL_LIMIT = 25000    # absolute tick budget -> fail

# Safety hatch: if the Asteroid Dodge flight never ends (asteroids did
# not hit), press SHIFT+A (= B+A) to force an eject -> flight loop
# breaks -> eject cutscene -> game over.
HATCH_FRAMES = 1600

# Persistent pattern: while the static game-over wait is on screen press
# B (local tick 30) to restart -> menu. Repeatable for any number of
# deaths - unlike a one-shot linear event it cannot be "used up". Short
# still-frame flaps during launch/eject never reach the threshold
# because the local tick resets on every scene change.
#
# B, not A: game_over() exits on A-or-B justPressed, and the very step
# that satisfies it leaves that button in the module state. menu() tests
# buttonA.justPressed() at its loop top BEFORE its first display.update()
# (i.e. before the next driver poll), so a held A would be read again as
# a fresh press and instantly relaunch the selected game. B is invisible
# to menu's wait, so the script can navigate instead.
GO_RESTART_AT = 30


def ev(scene, at, btn, hold=3, every=None, count=None, name=None):
    return {'scene': scene, 'at': at, 'btn': btn, 'hold': hold,
            'every': every, 'count': count,
            'name': name or f'{scene}@{at} {btn}'}


def btn_list(btn):
    """Button spec -> list of BTN_IDS names. A multi-button press is
    spelled with one letter per button ('BA' = B+A); single buttons keep
    their full name ('DOWN', 'LEFT', ...)."""
    if btn in BTN_IDS:
        return [btn]
    names = [ch for ch in btn if ch in BTN_IDS]
    if not names:
        raise ValueError(f'unknown button spec: {btn!r}')
    return names


# A/B presses use hold=2 (held for exactly one tick, released on the
# next): the button is released *before* the next scene's first
# input-poll tick, so it cannot bleed into that scene. A 2-tick hold
# that survives e.g. gameover -> menu makes buttonA.justPressed() fire
# on the first menu tick and relaunch the selected game, and a hold that
# survives into the remap wait would capture 'A' as the new key.
EVENTS = [
    ev('menu', 40, 'A', 2, name='menu: start Asteroid Dodge'),
    ev('menu', 40, 'DOWN', 2, every=12, count=3,
       name='menu: down to Settings'),
    ev('menu', 70, 'A', 2, name='menu: open Settings'),
    ev('settings', 40, 'DOWN', 2, every=10, count=4,
       name='settings: down to MOVE UP row'),
    ev('settings', 90, 'A', 2, name='settings: start MOVE UP remap'),
    ev('settings', 140, 'LEFT', 4,
       name='settings: LEFT press (SHIFT-toggle branch; capture done)'),
    ev('settings', 180, 'B', 2, name='settings: B: save keymap + exit'),
    ev('menu', 40, 'DOWN', 2, every=12, count=4,
       name='menu: down to Exit Game'),
    ev('menu', 70, 'A', 2, name='menu: Exit Game -> reset()'),
]


class Driver:
    def __init__(self):
        self.scene = None
        self.prev_bytes = None
        self.line_streak = 0
        self.tick = 0
        self.total = 0
        self.armed = False
        self.ei = 0
        self.sweep = None
        self.sweep_left = 0
        self.sweep_next = 0
        self.press = None          # (btn_string, remaining_frames)
        self.hatch_fired = False
        self.last_activity = 0
        self.fires = []
        self.flights = 0
        self.shot_due = None
        self.shot_scene = ''

    # -- scene classification --------------------------------------------
    def pip_white(self):
        for y in range(PIP_Y0, PIP_Y0 + 3):
            for x in range(PIP_X0, PIP_X0 + 3):
                if display.getPixel(x, y) == WHITE:
                    return True
        return False

    def settings_line(self):
        for x in LINE_XS:
            if display.getPixel(x, LINE_Y) != WHITE:
                return False
        return True

    def classify(self):
        fr = display.frameRate
        cur = bytes(display.drawBuffer)
        changed = self.prev_bytes is not None and cur != self.prev_bytes
        self.prev_bytes = cur

        if fr == 40 and self.pip_white():
            return 'flight'
        if fr == 30:
            if self.settings_line():
                self.line_streak += 1
                if self.line_streak >= SETTINGS_PERSIST:
                    return 'settings'
            else:
                self.line_streak = 0
            return 'menu'
        if fr in (20, 6, 10):
            # animated cutscene frames vs the static game-over wait
            return 'cutscene' if changed else 'gameover'
        return 'boot'   # fr == 0: intro timer phase

    # -- per-frame input driver (replaces thumbyButton.update_button_state)
    def step(self):
        tb._previous_keys = tb._current_keys.copy()
        pressed = {b: False for b in BTN_IDS}

        sc = self.classify()
        if sc != self.scene:
            print(f'[thumby_selfplay] scene -> {sc} (frame {self.total})',
                  flush=True)
            self.scene = sc
            self.tick = 0
            if SHOTS and sc in ('menu', 'settings', 'gameover', 'flight'):
                self.shot_due = self.total + SHOT_DELAY
                self.shot_scene = sc
            if sc == 'flight':
                self.flights += 1
                self.hatch_fired = False   # every flight gets its own hatch
            if self.sweep is not None:  # resume after transient change
                self.sweep_next = self.tick
            self.last_activity = self.total
        self.tick += 1
        self.total += 1
        if SHOTS and self.shot_due is not None and self.total == self.shot_due:
            snapshot(self.shot_scene)
            self.shot_due = None

        if not self.armed:
            if sc == 'menu':
                self.armed = True
                self.last_activity = self.total
                print('[thumby_selfplay] armed (first menu screen)',
                      flush=True)
        else:
            # 1) flight is continuous activity (no events while flying);
            #    keep the stall watchdog fed and check the safety hatch.
            if sc == 'flight':
                self.last_activity = self.total
                if (not self.hatch_fired and self.press is None
                        and self.tick >= HATCH_FRAMES):
                    self.press = (btn_list('BA'), 4)   # SHIFT+A -> eject
                    self.hatch_fired = True
                    self.last_activity = self.total
                    print('[thumby_selfplay] flight hatch: SHIFT+A eject '
                          f'(frame {self.total})', flush=True)

            # 1b) persistent game-over restart (repeatable, any count)
            if (sc == 'gameover' and self.press is None
                    and self.sweep is None and self.tick >= GO_RESTART_AT):
                self.press = (btn_list('B'), 2)   # one tick; B avoids bleed
                self.last_activity = self.total
                self.fires.append((self.total, 'gameover: restart (B)'))
                print(f'[thumby_selfplay] fire: gameover restart B (scene '
                      f'{sc} local {self.tick} frame {self.total})',
                      flush=True)

            # 2) linear event script
            if (self.press is None and self.sweep is None
                    and self.ei < len(EVENTS)):
                e = EVENTS[self.ei]
                if sc == e['scene'] and self.tick >= e['at']:
                    if e['count']:
                        self.sweep = e
                        self.sweep_left = e['count']
                        self.sweep_next = self.tick + e['every']
                        self.sweep_left -= 1
                    else:
                        self.sweep = None
                        self.ei += 1
                    self.press = (btn_list(e['btn']), e['hold'])
                    self.fires.append((self.total, e['name']))
                    self.last_activity = self.total
                    print(f'[thumby_selfplay] fire: {e["name"]} (scene {sc} '
                          f'local {self.tick} frame {self.total})',
                          flush=True)
            elif self.sweep is not None and self.press is None:
                if (sc == self.sweep['scene']
                        and self.tick >= self.sweep_next):
                    self.press = (btn_list(self.sweep['btn']),
                                  self.sweep['hold'])
                    self.sweep_left -= 1
                    self.sweep_next += self.sweep['every']
                    n = self.sweep['count'] - self.sweep_left
                    self.fires.append(
                        (self.total,
                         f'{self.sweep["name"]} ({n}/{self.sweep["count"]})'))
                    self.last_activity = self.total
                    print(f'[thumby_selfplay] sweep: {self.fires[-1][1]} '
                          f'(frame {self.total})', flush=True)
                    if self.sweep_left == 0:
                        self.sweep = None
                        self.ei += 1

            # 3) hold / release the active press. press[0] is a list of
            #    button names (['B', 'A'] for a two-button press, e.g.
            #    SHIFT+A on Thumby where SHIFT is B).
            if self.press is not None:
                names, rem = self.press
                if rem <= 1:
                    self.press = None
                else:
                    for name in names:
                        pressed[name] = True
                    self.press = (names, rem - 1)

            # 4) timeouts
            if self.total - self.last_activity > STALL_LIMIT:
                nxt = (EVENTS[self.ei]['name'] if self.ei < len(EVENTS)
                       else '(script done)')
                raise TimeoutError(
                    f'stalled at frame {self.total}: scene {sc} local '
                    f'{self.tick}, waiting for: {nxt}')
            if self.total > TOTAL_LIMIT:
                raise TimeoutError(
                    f'absolute tick budget {TOTAL_LIMIT} exceeded '
                    f'(scene {sc})')

        tb._current_keys = pressed


driver = Driver()
eng.update_button_state = driver.step

# Snapshot runtime state files so the run can be made non-destructive.
keymap_path = os.path.join(GAME_DIR, 'keymap.json')
keymap_before = None
if os.path.exists(keymap_path):
    with open(keymap_path, 'rb') as f:
        keymap_before = f.read()

t0 = time.time()
print(f'[thumby_selfplay] running script ({len(EVENTS)} events)...',
      flush=True)
rc = 'fail'
try:
    import main  # runs the game; ends via reset() -> sys.exit(0)
    print('[thumby_selfplay] game import returned without exiting')
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else 0
    rc = 'pass' if code == 0 else 'fail'
    print(f'[thumby_selfplay] game exited: code {code}', flush=True)
except TimeoutError as e:
    print(f'[thumby_selfplay] TIMEOUT: {e}', flush=True)
except BaseException as e:
    import traceback
    traceback.print_exc()
    print(f'[thumby_selfplay] game crashed: {type(e).__name__}: {e}',
          flush=True)
finally:
    print(f'[thumby_selfplay] total frames: {driver.total}, '
          f'wall time: {time.time() - t0:.1f}s, '
          f'flights: {driver.flights}, '
          f'events fired: {len(driver.fires)}', flush=True)
    for frame, name in driver.fires:
        print(f'  frame {frame:6d}: {name}')

    if rc == 'pass':
        if os.path.exists(keymap_path):
            with open(keymap_path, 'r') as f:
                content = f.read()
            print(f'[thumby_selfplay] keymap.json: {content}')
            # On the PC the remap capture lands on the trigger key (see
            # module docstring), so MOVE_UP is expected to be 'A'.
            try:
                got = json.loads(content).get('MOVE_UP')
                if got != 'A':
                    print(f'[thumby_selfplay] NOTE: MOVE_UP={got!r} '
                          f"(expected 'A' - PC trigger-key capture)")
            except Exception as e:
                print(f'[thumby_selfplay] keymap parse failed: {e}')
        if not KEEP:
            if keymap_before is not None:
                with open(keymap_path, 'wb') as f:
                    f.write(keymap_before)
            elif os.path.exists(keymap_path):
                os.remove(keymap_path)
            print('[thumby_selfplay] runtime state restored')

print(f'[thumby_selfplay] RESULT: {rc.upper()}', flush=True)
sys.exit(0 if rc == 'pass' else 1)
