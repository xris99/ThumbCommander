#!/usr/bin/env python3
"""
PC launcher for the ThumbCommander games (ThumbyColor + Thumby editions).

Runs the *same* game source as the hardware targets on a PC, backed by
the CPython/pygame firmware emulation in thumby_engine.pc. Two modes:

  --mode color   (default) ThumbyColor: 128x128 RGB565, 9 buttons, audio
  --mode thumby           original Thumby: 72x40, 4-level grayscale,
                          6 buttons, no audio (the game's unmodified
                          Thumby code path drives it)

The launcher does three things and then hands over to the game:

  1. puts the repository root and the game directory on sys.path and
     (for --headless) installs the SDL dummy drivers *before* pygame is
     first imported; --scale sets THUMBY_SCALE (window magnification
     for the Thumby panel, default 6 -> 432x240);
  2. calls thumby_engine.pc.bootstrap() with the game directory and the
     mode: firmware module emulation and chdir into the game directory
     (so runtime state such as keymap.json / settings.json lands next
     to the game);
  3. runs the FPS calibration for the selected mode (measures how much
     your machine is slower than the target rate and stores the
     correction per mode in .pc_wrapper_settings.json) unless a saved
     value is present.

Then it imports the game (main .py, a 3-line shim that imports
MainGame); MainGame's trailing main() call starts the game loop.
Ctrl+C / window close exits.

Usage:
    python3 tool/run_pc.py                 # ThumbCommander color (window+audio)
    python3 tool/run_pc.py --mode thumby   # ThumbCommander on a virtual Thumby
    python3 tool/run_pc.py --game mariocards
    python3 tool/run_pc.py --recalibrate   # redo the FPS calibration
    python3 tool/run_pc.py --headless      # no window, no sound (CI)

Controls (see thumby_engine/pc/README.md):
    color:   Arrows - d-pad          Y - A (fire)  X - B
             A - left bumper   S - right bumper    ESC - menu
    thumby:  Arrows - d-pad          Y - A (fire)  X - B
             (Thumby has no bumpers/menu button; LB/RB/MENU are
             aliased to L/R/B by the platform module)
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(
        description='Run a ThumbCommander game (ThumbyColor or Thumby '
                    'edition) on a PC.',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game', default='thumbcommander',
                    help='game under games/ to run (default: thumbcommander)')
    ap.add_argument('--mode', choices=('color', 'thumby'), default='color',
                    help='emulation target: ThumbyColor (default) or the '
                         'original Thumby (72x40, 4-level grayscale, 6 keys)')
    ap.add_argument('--scale', type=int, default=None,
                    help='window magnification for the Thumby panel '
                         '(default 6 -> 432x240; ignored in color mode)')
    ap.add_argument('--recalibrate', action='store_true',
                    help='force the FPS calibration to run again')
    ap.add_argument('--headless', action='store_true',
                    help='SDL dummy video/audio drivers (no window, no sound)')
    args = ap.parse_args()

    if args.headless:
        # Must be set before pygame is imported anywhere
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    if args.scale:
        os.environ['THUMBY_SCALE'] = str(args.scale)

    game_dir = os.path.join(REPO_ROOT, 'games', args.game)
    if not os.path.isdir(game_dir):
        raise SystemExit(f'error: game directory not found: {game_dir} '
                         f'(looked under {REPO_ROOT}/games/)')

    print('=' * 60)
    if args.mode == 'color':
        print(f'ThumbCommander - {args.game} (ThumbyColor edition, PC)')
        print('=' * 60)
        print('  Arrows: d-pad   Y: A (fire)   X: B')
        print('  A: left bumper   S: right bumper   ESC: menu / quit')
    else:
        print(f'ThumbCommander - {args.game} (original Thumby, 72x40 '
              f'4-level grayscale, PC)')
        print('=' * 60)
        print('  Arrows: d-pad   Y: A (fire)   X: B')
        print('  Thumby has no bumpers/menu - LB/RB/MENU alias to L/R/B')
    print()

    sys.path.insert(0, REPO_ROOT)

    # Firmware emulation + chdir into the game dir.
    from thumby_engine.pc import bootstrap
    bootstrap(local_root=game_dir, mode=args.mode)

    # The game's own directory on sys.path: bootstrap chdir'd there, but
    # in script mode the cwd is not added to sys.path, so the `import main`
    # below needs it explicitly.
    if game_dir not in sys.path:
        sys.path.insert(0, game_dir)

    # FPS calibration (plays the intro cutscene once, without audio,
    # to measure rendering overhead). Skipped when a value is saved.
    from thumby_engine.pc import fps_calibration
    try:
        if args.recalibrate:
            fps_calibration.recalibrate()
        else:
            fps_calibration.get_fps_correction()
    except Exception as e:
        print(f'[Launcher] FPS calibration failed ({e}); '
              f'continuing with the uncorrected rate')

    # The game: importing main.py (a 3-line shim) imports MainGame,
    # whose top-level code (display setup, intro cutscene, ...) and
    # trailing main() call start the loop.
    import main  # noqa: F401
    print('\n[Launcher] Game exited cleanly.')


if __name__ == '__main__':
    main()
