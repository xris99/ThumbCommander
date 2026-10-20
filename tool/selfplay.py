#!/usr/bin/env python3
"""
selfplay.py - headless scripted self-play test for the PC target.

Boots a game (default: mariocards) exactly like tool/run_pc.py does,
then replaces the PC input polling (engine.tick ->
thumbyButton.update_button_state) with a scene-aware script driver and
plays a full session:

    title -> kart select -> battle (auto-plays the first card)
    -> result (rematch) -> battle -> result -> title
    -> settings: remap LEFT to LB, walk down, save on BACK row, exit
    -> settings: walk down to QUIT -> reset() -> clean exit (code 0)

Scene classification uses pixel probes on the RGB565 framebuffer:

    settings  pixel(2,14)  == 0x7BF2  (DIM divider below the header)
    result    pixel(4,116) toggles    (animated checker strip)
    battle    pixel(2,11)  != BG      (HP pips, or full damage flash)
    select    pixel(27,28) == 0xFF60  (kart highlight box)
    title     everything else (incl. the first-battle help overlay)

Success = the scripted QUIT makes the game call reset(), which exits
the process with code 0. The run mutates keymap.json (LEFT -> LB) and
creates settings.json; their content is printed and keymap.json is
restored to its pre-run state afterwards (use -k to keep mutations).
"""

import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = 'mariocards'
KEEP = False
for a in sys.argv[1:]:
    if a.startswith('--game='):
        GAME = a.split('=', 1)[1]
    elif a == '-k':
        KEEP = True
    elif not a.startswith('-'):
        GAME = a

GAME_DIR = os.path.join(REPO, 'games', GAME)
if not os.path.isdir(GAME_DIR):
    sys.exit(f'selfplay: unknown game "{GAME}" (no games/{GAME})')

# Headless SDL (same as run_pc --headless)
os.environ['SDL_VIDEODRIVER'] = 'dummy'

sys.path.insert(0, REPO)
from thumby_engine.pc import bootstrap

print(f'[selfplay] booting game: {GAME}')
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

FB = display.internal_fb
BG, DIM, SEL = 0x2967, 0x7BF2, 0xFF60
BTN_IDS = ('A', 'B', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'LB', 'RB', 'MENU')


def ev(scene, at, btn, hold=3, every=None, count=None, name=None):
    return {'scene': scene, 'at': at, 'btn': btn, 'hold': hold,
            'every': every, 'count': count,
            'name': name or f'{scene}@{at} {btn}'}


EVENTS = [
    ev('title', 60, 'A', name='title: START'),
    ev('select', 60, 'A', name='select: pick kart'),
    ev('title', 60, 'A', name='help overlay: dismiss'),
    ev('result', 40, 'A', name='result: rematch'),
    ev('result', 40, 'B', name='result: back to title'),
    ev('title', 60, 'B', name='title: SETTINGS'),
    ev('settings', 30, 'A', name='settings: remap LEFT'),
    ev('settings', 42, 'LB', name='settings: capture new key (LB)'),
    ev('settings', 60, 'DOWN', 2, every=12, count=9,
       name='settings: sweep down to QUIT'),
    ev('settings', 190, 'DOWN', 2, name='settings: to BACK row'),
    ev('settings', 210, 'A', name='settings: BACK row (save + exit)'),
    ev('title', 60, 'B', name='title: SETTINGS (2nd)'),
    ev('settings', 30, 'DOWN', 2, every=12, count=9,
       name='settings: sweep down to QUIT (2nd)'),
    ev('settings', 150, 'A', name='settings: QUIT -> reset()'),
]

# Persistent pattern: while a battle is on screen, press A every 20
# local ticks starting at 40. A is ignored by the game outside
# ST_CHOOSE, so this simply plays one card per round.
BATTLE_AT, BATTLE_EVERY, BATTLE_HOLD = 40, 20, 3

STALL_LIMIT = 3000     # ticks without fire / scene change -> fail
TOTAL_LIMIT = 25000    # absolute tick budget -> fail


class Driver:
    def __init__(self):
        self.scene = None
        self.prev116 = None
        self.pprev116 = None
        self.tick = 0
        self.total = 0
        self.armed = False
        self.ei = 0
        self.sweep = None
        self.sweep_left = 0
        self.sweep_next = 0
        self.press = None
        self.last_activity = 0
        self.fires = []
        self.battle_presses = 0

    # -- scene classification --------------------------------------------
    def pixel(self, x, y):
        return FB.pixel(x, y)

    def classify(self):
        p14 = self.pixel(2, 14)
        p11 = self.pixel(2, 11)
        p28 = self.pixel(27, 28)
        p116 = self.pixel(4, 116)
        # The checker strip toggles every result frame; require two
        # consecutive changes so one-frame scene-transition blips
        # (e.g. cutscene -> title) do not classify as result.
        toggling = (self.prev116 is not None and self.pprev116 is not None
                    and p116 != self.prev116
                    and self.prev116 != self.pprev116)
        if p14 == DIM:
            sc = 'settings'
        elif toggling:
            sc = 'result'
        elif p11 != BG:
            sc = 'battle'
        elif p28 == SEL:
            sc = 'select'
        else:
            sc = 'title'
        self.pprev116 = self.prev116
        self.prev116 = p116
        return sc

    # -- per-frame input driver (replaces thumbyButton.update_button_state)
    def step(self):
        tb._previous_keys = tb._current_keys.copy()
        pressed = {b: False for b in BTN_IDS}

        sc = self.classify()
        if sc != self.scene:
            print(f'[selfplay] scene -> {sc} (frame {self.total})',
                  flush=True)
            self.scene = sc
            self.tick = 0
            if self.sweep is not None:  # resume after transient change
                self.sweep_next = self.tick
            self.last_activity = self.total
        self.tick += 1
        self.total += 1

        if not self.armed:
            if sc == 'title':
                self.armed = True
                self.last_activity = self.total
                print('[selfplay] armed (first title screen)', flush=True)
        else:
            # 1) persistent battle pattern
            if (sc == 'battle' and self.press is None
                    and self.tick >= BATTLE_AT
                    and (self.tick - BATTLE_AT) % BATTLE_EVERY == 0):
                self.press = ('A', BATTLE_HOLD)
                self.battle_presses += 1
                self.last_activity = self.total

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
                    self.press = (e['btn'], e['hold'])
                    self.fires.append((self.total, e['name']))
                    self.last_activity = self.total
                    print(f'[selfplay] fire: {e["name"]} (scene {sc} '
                          f'local {self.tick} frame {self.total})',
                          flush=True)
            elif self.sweep is not None and self.press is None:
                if (sc == self.sweep['scene']
                        and self.tick >= self.sweep_next):
                    self.press = (self.sweep['btn'], self.sweep['hold'])
                    self.sweep_left -= 1
                    self.sweep_next += self.sweep['every']
                    n = self.sweep['count'] - self.sweep_left
                    self.fires.append(
                        (self.total,
                         f'{self.sweep["name"]} ({n}/{self.sweep["count"]})'))
                    self.last_activity = self.total
                    print(f'[selfplay] sweep: {self.fires[-1][1]} '
                          f'(frame {self.total})', flush=True)
                    if self.sweep_left == 0:
                        self.sweep = None
                        self.ei += 1

            # 3) hold / release the active press
            if self.press is not None:
                btn, rem = self.press
                if rem <= 1:
                    self.press = None
                else:
                    pressed[btn] = True
                    self.press = (btn, rem - 1)

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
settings_path = os.path.join(GAME_DIR, 'settings.json')
settings_before = os.path.exists(settings_path)

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
          f'battle A-presses: {driver.battle_presses}, '
          f'events fired: {len(driver.fires)}', flush=True)
    for frame, name in driver.fires:
        print(f'  frame {frame:6d}: {name}')

    if rc == 'pass':
        for p, label in ((keymap_path, 'keymap.json'),
                         (settings_path, 'settings.json')):
            if os.path.exists(p):
                with open(p, 'r') as f:
                    print(f'[selfplay] {label}: {f.read()}')
        if not KEEP:
            if keymap_before is not None:
                with open(keymap_path, 'wb') as f:
                    f.write(keymap_before)
            elif os.path.exists(keymap_path):
                os.remove(keymap_path)
            if not settings_before and os.path.exists(settings_path):
                os.remove(settings_path)
            print('[selfplay] runtime state restored')

print(f'[selfplay] RESULT: {rc.upper()}', flush=True)
sys.exit(0 if rc == 'pass' else 1)
