# PC Target — CPython/pygame Emulation of the ThumbyColor Firmware

The `thumby_engine.pc` package lets the *same* engine and game source that
runs on a ThumbyColor run unmodified on a PC (CPython + pygame). It
emulates the firmware modules the engine and games import:

| Firmware module | Emulated by            | Notes                                            |
|-----------------|------------------------|--------------------------------------------------|
| `micropython`   | `micropython_compat.py`| `@viper`/`@native`/`@baseline` no-op decorators, `const`, `ptr8/16/32`, `array` 'O' typecode |
| `utime` / `time`| `utime.py`             | MicroPython-style `ticks_ms/us/diff`, 32-bit wrap |
| `machine`       | `machine.py`           | `Pin`, `Timer` (threaded), `SPI` stubs, `freq()` no-op |
| `gc`            | `gc_compat.py`         | `collect()` / `mem_free()` wrappers over CPython gc |
| `framebuf`      | `framebuf.py`          | `FrameBuffer` with RGB565/GS8, blit, text (8x8 builtin font) |
| `engine`        | `engine.py`            | `tick()` / `time_to_next_tick()` / `fps_limit()` with FPS-correction factor |
| `engine_io`     | `engine_io.py`         | The 9 button ID constants (also the ThumbyColor platform *detector*) |
| `engine_draw`   | `engine_draw.py`       | `back_fb()` → pygame window (scaled RGB565→RGB888 blit) |
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
5. `chdir()`s into the game directory (same as the firmware does on the
   device before running `main.py`), so runtime state
   (`keymap.json`, `settings.json`, `.pc_wrapper_settings.json`,
   `campaign_saves.json`) is written next to the game.

It is idempotent. The launcher (`tool/run_pc.py`) is the sole entry point
on the PC and calls it before importing the game; the platform module
never knows it runs on a PC - to it, the emulation is just a ThumbyColor.

## Running a game

```bash
# from the repository root
python3 tool/run_pc.py              # runs games/thumbcommander
python3 tool/run_pc.py --recalibrate
python3 tool/run_pc.py --headless   # SDL dummy video/audio (CI)
```

The launcher: (a) calls `bootstrap()`, (b) runs a one-time FPS
calibration (plays the intro cutscene to measure rendering overhead and
saves a correction factor to `.pc_wrapper_settings.json`, which
`pc/engine.py` applies to `fps_limit()`; `--recalibrate` forces it), and
(c) imports the game's `main` module, whose trailing `main()` call starts
the game.

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

## Requirements

- Python 3.8+
- pygame 2.0+ (`pip install -r requirements.txt` from the repository root)

## Limitations

- Rendering is per-pixel in Python, so absolute performance is far below
  the RP2350 hardware; the FPS calibration compensates the *relative*
  overhead of the window blit.
- No rumble (no haptics on a PC).
- The 8x8 text font is built into `framebuf.py`; the font *file* a game
  loads only affects the glyph count/width bookkeeping, not the glyphs.
