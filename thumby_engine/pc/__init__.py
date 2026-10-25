# thumby_engine.pc - CPython/pygame emulation of the Thumby firmware
# modules, so the *same* engine and game source runs unmodified on a PC.
#
# Two emulation modes:
#   * 'color'  (default) - the emulation registers an `engine_io` module,
#     so thumby_engine.platform takes its ThumbyColor branch: 128x128
#     RGB565 display, 9 buttons, pygame audio, TDL8 cutscenes.
#   * 'thumby' - the emulation does NOT register `engine_io`, and instead
#     registers the CPython port of the grayscale driver under the package
#     module name thumby_engine.display.grayscale, so platform takes its
#     *original-Thumby* branch: 72x40, 4-level dither, 6 buttons, no audio,
#     silent 1-bit cutscenes. The game source runs unmodified either way.
#
# bootstrap() is the single entry point for the PC target:
#   1. puts the repository root on sys.path (so `import thumby_engine` works)
#   2. installs the MicroPython compatibility layer (micropython, const,
#      ptr8/16/32, array 'O' typecode)
#   3. registers the firmware module emulations in sys.modules under their
#      firmware names: utime/time, machine, gc, framebuf, engine, engine_io,
#      engine_draw, _thread, audio, thumbyButton, thumbyHardware - plus the
#      pygame audio module under thumby_engine.audio.hardware, so the
#      platform module's audio import transparently picks it up (and in
#      thumby mode the grayscale display under thumby_engine.display.grayscale)
#   4. chdirs into the game directory (runtime state: keymap.json,
#      settings.json, .pc_wrapper_settings.json, ...)
#
# The launcher (tool/run_pc.py) is the sole entry point on the PC: it
# calls bootstrap() before importing the game. The platform module never
# knows it runs on a PC - to it, the emulation is just the selected target.

import sys
import os

_bootstrapped = False


def _repo_root():
    # <repo>/thumby_engine/pc/__init__.py  ->  <repo>
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def bootstrap(local_root=None, mode='color'):
    """Install the firmware emulation (idempotent).

    Args:
        local_root: game directory to chdir into (runtime state files)
        mode: 'color' = ThumbyColor emulation (registers engine_io);
              'thumby' = original-Thumby emulation (omits engine_io and
              registers the grayscale display port instead)
    """
    global _bootstrapped
    if _bootstrapped:
        return
    if getattr(sys, 'implementation', None) is None or \
            sys.implementation.name != 'cpython':
        raise RuntimeError('thumby_engine.pc only works on CPython')
    if mode not in ('color', 'thumby'):
        raise ValueError(f"unknown emulation mode {mode!r} "
                         f"(expected 'color' or 'thumby')")

    if local_root is None:
        local_root = os.path.join(_repo_root(), 'games', 'thumbcommander')

    # 1. Repo root on sys.path (for `import thumby_engine` and friends)
    root = _repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    # 2. Keep a reference to the stdlib time BEFORE we replace it in
    #    sys.modules (needed by fps_calibration and by the modules below,
    #    which must see the real time when they are imported).
    import time as _stdlib_time
    sys.modules['_stdlib_time_backup'] = _stdlib_time

    # 3. MicroPython compatibility layer (must come first: it patches
    #    builtins and the array module that the emulation modules use)
    from . import micropython_compat  # noqa: F401

    # 4. Import all firmware module emulations (still under CPython rules,
    #    so their `import time` etc. bind the real stdlib modules)
    from . import utime
    from . import machine
    from . import gc_compat
    from . import framebuf
    from . import engine
    from . import engine_io
    from . import engine_draw
    from . import grayscale_display
    from . import _thread
    from . import thumbyButton
    from . import thumbyHardware
    from ..audio import pc as audio

    # 5. Register them in sys.modules under the firmware module names that
    #    the engine and game import
    sys.modules['utime'] = utime
    sys.modules['time'] = utime
    sys.modules['machine'] = machine
    sys.modules['gc'] = gc_compat
    sys.modules['framebuf'] = framebuf
    sys.modules['engine'] = engine
    sys.modules['engine_draw'] = engine_draw
    sys.modules['_thread'] = _thread
    sys.modules['audio'] = audio
    # The platform module imports its audio backend by package path;
    # alias the pygame module there so the same import picks it up.
    sys.modules['thumby_engine.audio.hardware'] = audio
    sys.modules['thumbyButton'] = thumbyButton
    sys.modules['thumbyHardware'] = thumbyHardware

    # Mode selection (read by engine/fps_calibration for the per-mode
    # FPS correction key):
    os.environ['THUMBY_EMULATION_MODE'] = mode
    if mode == 'thumby':
        # No engine_io -> platform detects IS_THUMBY. The import machinery
        # checks sys.modules first for the resolved absolute name, so this
        # registration makes the platform module's `from ..display.grayscale
        # import Grayscale, Sprite, create_sprite` resolve to the CPython
        # port instead of the RP2040 hardware driver (same trick as the
        # audio alias above).
        sys.modules['thumby_engine.display.grayscale'] = grayscale_display
    else:
        sys.modules['engine_io'] = engine_io

    # 6. Runtime state (keymap.json, settings.json, .pc_wrapper_settings.json,
    #    campaign_saves.json) is written relative to cwd
    os.chdir(local_root)

    _bootstrapped = True
    label = 'ThumbyColor' if mode == 'color' else 'Thumby (72x40, 4-level)'
    print(f"[PC] {label} emulation ready ({local_root})")
