# PC Target — CPython/pygame Emulation of the Thumby Firmware

The `thumby_engine.pc` package lets the *same* engine and game source run
unmodified on a PC (CPython + pygame) against **either** target:

- **`color`** (default) - ThumbyColor: 128x128 RGB565, 9 buttons, audio,
  TDL8 color cutscenes.
- **`thumby`** - the original Thumby (RP2040): 72x40, 4-level grayscale,
  6 buttons, no audio, silent 1-bit cutscenes.

It emulates the firmware modules the engine and games import:

| Firmware module | Emulated by            | Notes                                            |
|-----------------|------------------------|--------------------------------------------------|
| `micropython`   | `micropython_compat.py`| `@viper`/`@native`/`@baseline` no-op decorators, `const`, `ptr8/16/32`, `array` 'O' typecode |
| `utime` / `time`| `utime.py`             | MicroPython-style `ticks_ms/us/diff`, 32-bit wrap |
| `machine`       | `machine.py`           | `Pin`, `Timer` (threaded), `SPI` stubs, `freq()` no-op |
| `gc`            | `gc_compat.py`         | `collect()` / `mem_free()` wrappers over CPython gc |
| `framebuf`      | `framebuf.py`          | `FrameBuffer` with RGB565/GS8, blit, text (8x8 builtin font) |
| `engine`        | `engine.py`            | `tick()` / `time_to_next_tick()` / `fps_limit()` with a *per-mode* FPS-correction factor |
| `engine_io`     | `engine_io.py`         | The 9 button ID constants; registered in color mode only - its presence is the platform's ThumbyColor *detector* |
| `engine_draw`   | `engine_draw.py`       | `back_fb()` → pygame window (color: RGB565→RGB888 blit; thumby: two bitplanes → 4-level grays) |
| `thumby_engine.display.grayscale` | `grayscale_display.py` | CPython port of the Thumby `Grayscale` driver (`Grayscale`, `Sprite`, `create_sprite`); registered only in thumby mode; also serves the vendored firmware fonts and the emulated device render cost |
| `_thread`       | `_thread.py`           | `start_new_thread()` / lock primitives |
| `audio`         | `thumby_engine.audio.pc`| pygame.mixer IMA-ADPCM decoder @ 15625 Hz, `open_id`/`play_id`/`close_ids` |
| `thumbyButton`  | `thumbyButton.py`      | `ButtonClass` over keyboard state, polled once per `tick()` |
| `thumbyHardware`| `thumbyHardware.py`    | Original-Thumby `sw*` switch stubs, `reset()` exits |

## How it works

`bootstrap()` (this package's `__init__`) is the single entry point:

1. Puts the repository root on `sys.path` so `import thumby_engine` works.
2. Saves the stdlib `time` as `sys.modules['_stdlib_time_backup']` (used by
   `fps_calibration.py`).
3. Imports all emulation modules **before** swapping `sys.modules`, so their
   own `import time` binds the real stdlib module.
4. Registers them in `sys.modules` under the *firmware* names
   (`time`→`utime`, `audio`→pygame module, …), so `import time`,
   `import engine`, … in engine and game code resolve to the emulations.
5. Selects the target from `bootstrap(mode=...)` and exports it as
   `THUMBY_EMULATION_MODE` (`engine.py` and `fps_calibration.py` pick
   their per-mode settings key from it):
   - `color`: registers `engine_io`, so `thumby_engine.platform` takes
     its ThumbyColor branch.
   - `thumby`: omits `engine_io` and registers `grayscale_display.py`
     under `thumby_engine.display.grayscale` (the same import-alias
     trick as the audio backend), so platform takes its *original-
     Thumby* branch (72x40, 4-level, 6 buttons, no audio).
6. `chdir()`s into the game directory (same as the firmware does on the
   device before running `main.py`), so runtime state
   (`keymap.json`, `settings.json`, `.pc_wrapper_settings.json`,
   `campaign_saves.json`) is written next to the game.

It is idempotent. The launcher (`tool/run_pc.py`) is the sole entry point
on the PC and calls it before importing the game; the platform module
never knows it runs on a PC - to it, the emulation is just the selected
target: a ThumbyColor or an original Thumby.

## Running a game

```bash
# from the repository root
python3 tool/run_pc.py                    # ThumbCommander (color)
python3 tool/run_pc.py --mode thumby      # ThumbCommander on a virtual Thumby
python3 tool/run_pc.py --game mariokart   # another game (color)
python3 tool/run_pc.py --mode thumby --scale 8   # window magnification
python3 tool/run_pc.py --recalibrate
python3 tool/run_pc.py --headless   # SDL dummy video/audio (CI)
```

The launcher: (a) calls `bootstrap(local_root=game_dir, mode=...)`,
(b) runs a one-time FPS calibration **per mode** - color times the
color intro cutscene (target 21 fps) into the settings key
`fps_correction`, thumby times the grayscale intro
`intro_74_30.BIT.bin` (target 8 fps) into `fps_correction_thumby`;
saving merges into `.pc_wrapper_settings.json`, so calibrating one mode
never clobbers the other mode's value - and (c) imports the game's
`main` module, whose trailing `main()` call starts the game.
`pc/engine.py` applies the active mode's correction to `fps_limit()`
(e.g. `40 → 38.96`).

## Controls

| Keyboard key | ThumbyColor button |
|--------------|--------------------|
| Arrow keys   | D-Pad              |
| Y            | Button A (fire)    |
| X            | Button B           |
| A            | Left bumper (LB)   |
| S            | Right bumper (RB)  |
| ESC          | Menu               |

(A is mapped to `Y` because the reference keyboard layout is German
QWERTZ, where the physical `Z` key produces `Y`.)

In `--mode thumby` only these exist - the Thumby has 6 buttons and no
bumpers or menu button:

| Keyboard key | Thumby button |
|--------------|---------------|
| Arrow keys   | D-Pad         |
| Y            | Button A      |
| X            | Button B      |

The platform module aliases `LB`/`RB`/`MENU` to `LEFT`/`RIGHT`/`B` so
games that reference the color buttons still work; `SHIFT+A` (e.g. the
flight eject) is `B`+`A` held together.

## Thumby mode: panel rendering

`--mode thumby` drives the game's *unmodified* Thumby code path: the
platform detects the missing `engine_io`, builds the 72x40 `Grayscale`
display from the PC port of the RP2040 driver, and plays silent 1-bit
cutscenes (no audio at all).

`Grayscale.update()` pushes its two 1bpp column-major page bitplanes
(light plane + shading plane, 5 pages of 72 bytes for 40 rows) to
`engine_draw.blit_grayscale()`, which composes the hardware's 4 gray
levels and scales them to the window (default magnification 6 →
432x240; `--scale N` or `THUMBY_SCALE` change it):

| level | name       | window RGB      |
|-------|------------|-----------------|
| 0     | BLACK      | (0,0,0)         |
| 1     | WHITE      | (255,255,255)   |
| 2     | DARKGRAY   | (85,85,85)      |
| 3     | LIGHTGRAY  | (170,170,170)   |

The fast path is a palettized `pygame.image.frombuffer` + integer-scale
blit; it falls back to per-pixel rects automatically if the transform
fails. The boot intro animates from a `machine.Timer` callback thread
while the main thread may draw too, so window rendering is serialized by
a lock; a `QUIT` event exits via `os._exit(0)` because `sys.exit` there
would only kill the timer thread and leave the game stuck in the intro's
busy-wait join.

Device render-cost pacing: the real Thumby is render-bound - one frame
push (bitplanes + temporal-dither subframes) costs far more than the PC
window blit, so scenes whose frame period is below that cost run slower
than their `setFPS` target on the device (flight 40 → ~10 fps, menu 30 →
~10 fps), while period-bound scenes (game-over, cutscenes, the 8 fps
intro) are unaffected. `Grayscale.update()` sleeps that cost after each
blit to reproduce the device-realistic frame rate on the PC. Default
100 ms; `THUMBY_DEVICE_RENDER_MS` overrides it (`= 0` restores full
target speed).

The firmware font files (`/lib/font5x7.bin`, `/lib/font3x5.bin`) do not
exist on a PC, so this package vendors the **real** firmware fonts
(`pc/fonts/font3x5.bin`, `font5x7.bin`, `font8x8.bin` - taken from
`CoreThumbyFiles/lib` of the official TinyCircuits Thumby code-editor
simulator; `font5x7.bin` is byte-identical to the copy bundled by
`samclane/Thumbox`). Font resolution order: the requested path verbatim,
then the file's basename in the game directory / its `assets/` folder,
then the vendored firmware fonts, then a last-resort 8x8-downsampled
fallback. All-zero placeholder files (the shipped game font assets) are
skipped; the derived fallback prints a one-line notice per font, and the
default path never reaches it.

## E2E self-play test

`tool/thumby_selfplay.py` plays a full scripted session headless (the
`run_pc --mode thumby --headless` path): boot → menu → Asteroid Dodge
launch → flight (per-flight safety hatch: `SHIFT+A` eject if the flight
never ends) → eject cutscene → game over → Settings → `MOVE UP` remap →
keymap save → Exit Game → `reset()` → exit code 0. Scenes are classified
from the bitplane model itself (`display.frameRate`, the HUD life-pip
window, the settings divider row, whole-buffer change), every fired
event is printed, and `keymap.json` is restored after the run (`-k`
keeps the mutation). Color mode's equivalent is
`tool/mariokart_selfplay.py`. With the default render-cost emulation the
run takes roughly 3-4x longer on wall-clock than an unpaced one (~2.5
min); the tick-based watchdogs are unaffected.

One PC-specific input quirk is baked into the script: the PC button
module latches `_previous/_current` once per `engine.tick()`, so a game
loop that checks `justPressed()` at its loop top **before** its first
`display.update()` re-reads the previous step's state. Two consequences:
the game-over restart must press `B` (an `A` would be re-seen by the
menu's stale first check and instantly relaunch the selected game), and
the settings remap captures the *trigger* key - starting the remap
requires the latched state to report `A` justPressed, and the remap
wait's first `inputJustPressed()` sees exactly that state, so `MOVE UP`
comes out as `'A'`. Trigger and capture read the same latched state, so
no press duration can escape this; it is an artifact of the PC's
per-frame button latch. The harness asserts `MOVE_UP == 'A'` as the
expected PC outcome.

## Requirements

- Python 3.8+
- pygame 2.0+ (`pip install -r requirements.txt` from the repository root)

## Limitations

- Rendering is per-pixel in Python, so absolute performance is far below
  the RP2350 hardware; the FPS calibration compensates the *relative*
  overhead of the window blit.
- Thumby mode emulates the device's per-frame render cost by sleeping in
  `Grayscale.update()` (`THUMBY_DEVICE_RENDER_MS`, default 100 ms - see
  the panel-rendering section); set it to 0 to run at full target speed.
- No rumble (no haptics on a PC).
- The color path's 8x8 text font is built into `framebuf.py`; the font
  *file* a game loads there only affects the glyph count/width
  bookkeeping, not the glyphs. The Thumby/`Grayscale` path is different:
  the loaded (or vendored) font file fully determines the glyphs.
- Thumby mode has no audio (the real Thumby hardware has none), and its
  button module's per-frame state latch can leak input into loops that
  check `justPressed()` before their first `display.update()` (see the
  E2E section above).
- A process runs exactly one emulation mode; `back_fb()` keeps the first
  window geometry it was given.
