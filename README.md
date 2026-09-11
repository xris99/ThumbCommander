# ThumbCommander

A Wing Commander-style space combat game for the **Thumby** (RP2040,
72x40 1-bit dithered OLED) and the **ThumbyColor** (RP2350, 128x128
RGB565 with IMA-ADPCM audio), written in MicroPython. The same source
runs on both devices, and a CPython/pygame wrapper runs the
ThumbyColor version on a PC - there is no external ThumbyColor
emulator, the repo brings its own (tested on macOS, should work on any
desktop).

All content and game elements are taken from our friends at wcnews.com.

All keys can be remapped in the settings menu. Audio volume and
vibration can be set there as well. In default mode cutscenes can be
canceled with the MENU key (the B key on the Thumby).

## Repository layout

```
thumby_engine/           reusable engine - games never touch hardware directly
  platform/              the seam: detects Thumby / ThumbyColor / PC and
                         exports display, buttons, audio, sprites, cutscenes
  display/               grayscale.py (Thumby), color.py (ThumbyColor/PC)
  audio/                 hardware.py (ThumbyColor IMA-ADPCM), pc.py (pygame)
  cutscene/              grayscale / color cutscene players (TDL8 videos)
  util/                  fpmath (fixed point), stream_json (streamed JSON)
  pc/                    CPython/pygame firmware emulation (see pc/README.md)
games/thumbcommander/    the game
  main.py                entry shim - the firmware can only start
                         .py files, so this stays source: put the
                         game dir on sys.path (the firmware already
                         chdir'd into it), then import MainGame
  MainGame.py            the real entry point (menu -> missions -> repeat)
  constants.py           game constants (extend the shared PC object)
  campaign_engine.py     JSON campaign missions
  waypoint_system.py     guided flight paths
  intro.py               the 1-bit intro animation (Thumby only)
  color_enhancements.py  settings extras + FX (ThumbyColor/PC only)
  assets/                one flat directory: fonts, campaign JSONs,
                         1-bit .BIT/.SHD pairs, .COL.bin sprites,
                         .ima audio
tool/
  run_pc.py              PC launcher (bootstrap + FPS calibration + game)
  deploy.py              per-platform staging, mpy-cross compile, deploy
  grayscale_sprite_scaler.py  1-bit -> grayscale sprite tool
legacy/                  pre-refactor monolith, kept for reference
build/                   staging area created by deploy.py (gitignored)
```

### How the engine/game separation works

A game imports `thumby_engine.platform` (plus a couple of `util`
modules) and never imports a hardware driver directly. The platform
module detects the target at import time (`IS_THUMBY_COLOR`)
and wires the matching display, buttons, audio and cutscene
implementation into one shared `PC` constants object. Per-target
differences inside a game (color-only extras like the extended
settings menu) are selected with the same flags, so the
Thumby never pays the RAM cost of code it can't run.

### What gets deployed where

`tool/deploy.py` holds per-platform manifests: the Thumby gets the
grayscale display/cutscene and the 1-bit assets and no audio; the
ThumbyColor gets the color display/cutscene, the IMA audio driver and
the color assets - each taken from the one shared `assets/` directory,
selected by file extension. Anything a target never imports - most notably the
whole `thumby_engine.pc` emulation - is never copied or compiled. This
is what keeps the small-RAM devices small: on the device all deployed
code is mpy-cross bytecode, not RAM-resident Python source - with one
exception: the `main.py` entry shim, which the firmware requires
to be a `.py` file.

## Running on the PC

```bash
pip install -r requirements.txt    # pygame
python3 tool/run_pc.py             # ThumbyColor version, window + audio
python3 tool/run_pc.py --recalibrate
python3 tool/run_pc.py --headless  # SDL dummy video/audio (CI)
```

The launcher emulates the firmware (`thumby_engine.pc`) and chdirs
into the local game directory (as the firmware does on the device),
runs a one-time FPS calibration (stored in
`.pc_wrapper_settings.json`) and then imports the game (`main.py` ->
`MainGame.py`), whose trailing `main()` call starts the loop. Runtime state (keymap, settings,
campaign saves, calibration) is written next to the game. Details and
limitations: [thumby_engine/pc/README.md](thumby_engine/pc/README.md).

**Controls (PC)**

| Key       | Button                | Key      | Button              |
|-----------|-----------------------|----------|---------------------|
| Arrows    | D-pad                 | Y        | A (fire)            |
| X         | B                     | A / S    | left / right bumper |
| ESC       | menu / quit           |          |                     |

(A maps to `Y` because the reference layout is German QWERTZ, where the
physical `Z` key produces `Y`.)

## Deploying to a device

```bash
python3 tool/deploy.py                                 # stage + compile all platforms
python3 tool/deploy.py thumbycolor                     # one platform
python3 tool/deploy.py thumby --no-compile             # plain .py (debug only)
python3 tool/deploy.py thumbycolor --remote 192.168.1.42   # push via mpremote
```

The tool stages a per-platform image under `build/<platform>/` in the
device layout, compiles it with mpy-cross and with `--remote` pushes it
via mpremote. Every module becomes its own `.mpy` (mpy-cross has no
`--pack` - the flag never existed), so the engine deploys as a package
folder of `.mpy` files, which MicroPython imports just like a single
file. Each target is compiled with the matching `-march`: `armv6m`
for the Thumby (RP2040, Cortex-M0+) and `armv7emsp` for the
ThumbyColor (RP2350 - the arch the device firmware accepts); override
with `--arch` (e.g. `rv32imc` for the RP2350 RISC-V core). A compile
failure fails the deploy: the devices have too little RAM to fall
back to `.py` source.

Device layout after deployment:

```
:/lib/thumby_engine/      (the engine as a package of .mpy files)
:/Games/ThumbCommander/
  main.py                 (stays .py - the firmware can only start
                           .py; rename to __main__.py to auto-run
                           on boot)
  MainGame.mpy            (the real entry module)
  assets/...
```

`main.py` puts `/lib` on the import path on the device, matching the
`DEVICE_ENGINE_DIR` in `tool/deploy.py` - keep the two in sync when
you move the engine.

The `.mpy` format has been version **6.3** since MicroPython v1.19.1,
so any recent mpy-cross (e.g. the `mpy-cross` from pip) emits bytecode
the current Thumby/ThumbyColor firmware loads; the tool prints the
mpy-cross version it used.

## Building another game on the engine

1. Start from `games/thumbcommander/` as a template (or from scratch).
2. Import `thumby_engine.platform` for display, buttons, audio,
   sprites and cutscenes - never the hardware modules directly.
3. Keep all assets in the flat `assets/` directory; deploy.py
   selects the per-platform subset by file extension.
4. List your game modules and assets in a manifest in `tool/deploy.py`
   (one per target) so each device only receives what it imports.
5. Keep a small `main.py` shim that imports your real entry module:
   the firmware can only start `.py` files, and everything else
   should be compiled to `.mpy`.

## Reuse

Feel free to reuse the engine and the PC emulator to develop your own
games for the Thumby and ThumbyColor platforms.
