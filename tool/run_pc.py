#!/usr/bin/env python3
"""
PC launcher for ThumbCommander (ThumbyColor edition).

Runs the *same* game source as the ThumbyColor hardware target on a PC,
backed by the CPython/pygame firmware emulation in thumby_engine.pc.
The launcher does three things and then hands over to the game:

  1. puts the repository root and the game directory on sys.path and
     (for --headless) installs the SDL dummy drivers *before* pygame is
     first imported;
  2. calls thumby_engine.pc.bootstrap(): firmware module emulation and
     chdir into the game directory (so runtime state such as
     keymap.json / settings.json lands next to the game);
  3. runs the FPS calibration (measures how much your machine is slower
     than 60 FPS and stores the correction in .pc_wrapper_settings.json)
     unless a saved value is present.

Then it imports the game (main.py, a 3-line shim that imports
MainGame); MainGame's trailing main() call starts the game loop.
Ctrl+C / window close exits.

Usage:
    python3 tool/run_pc.py                 # normal run (window + audio)
    python3 tool/run_pc.py --recalibrate   # redo the FPS calibration
    python3 tool/run_pc.py --headless      # no window, no sound (CI)

Controls (see thumby_engine/pc/README.md):
    Arrows  - d-pad                Y - A (fire)      X - B
    A       - left bumper          S - right bumper  ESC - menu/quit
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(
        description='Run ThumbCommander (ThumbyColor) on a PC.',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--recalibrate', action='store_true',
                    help='force the FPS calibration to run again')
    ap.add_argument('--headless', action='store_true',
                    help='SDL dummy video/audio drivers (no window, no sound)')
    args = ap.parse_args()

    if args.headless:
        # Must be set before pygame is imported anywhere
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'

    print('=' * 60)
    print('ThumbCommander - ThumbyColor edition (PC)')
    print('=' * 60)
    print('  Arrows: d-pad   Y: A (fire)   X: B')
    print('  A: left bumper   S: right bumper   ESC: menu / quit')
    print()

    sys.path.insert(0, REPO_ROOT)

    # Firmware emulation + chdir into the game dir.
    from thumby_engine.pc import bootstrap
    bootstrap()

    # The game's own directory on sys.path: bootstrap chdir'd there, but
    # in script mode the cwd is not added to sys.path, so the `import main`
    # below needs it explicitly.
    game_dir = os.path.join(REPO_ROOT, 'games', 'thumbcommander')
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
