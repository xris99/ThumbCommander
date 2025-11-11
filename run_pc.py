#!/usr/bin/env python3
"""
ThumbCommander PC Launcher
Runs the ThumbyColor version of ThumbCommander on PC using pygame

This launcher sets up the MicroPython compatibility layer and launches the game
without modifying any of the game code.
"""

print("[Launcher] ========== LAUNCHER STARTING ==========", flush=True)

import sys
import os

print(f"[Launcher] Python version: {sys.version}", flush=True)
print(f"[Launcher] Platform: {sys.platform}", flush=True)

# CRITICAL: Set multiprocessing start method BEFORE any other imports
# This must be done before pygame or any module that might use multiprocessing
# NOTE: Do NOT call get_start_method() before set_start_method() - it locks the method!
import multiprocessing as mp

if sys.platform == 'darwin':
    # macOS: Force 'fork' method (needed for audio_loop function to be accessible in child process)
    # Note: macOS may show warnings about Core Foundation, but 'fork' is required for
    # the audio decoder process to access the audio_loop function
    try:
        mp.set_start_method('fork', force=True)
        print("[Launcher] Forced multiprocessing to use 'fork' method on macOS", flush=True)
    except Exception as e:
        print(f"[Launcher] ERROR: Could not force fork method: {e}", flush=True)
        print(f"[Launcher] WARNING: Audio may not work properly with spawn method", flush=True)
elif sys.platform != 'win32':
    # Linux/Unix: Use fork (default)
    try:
        mp.set_start_method('fork', force=False)
        print("[Launcher] Set multiprocessing to use 'fork' method", flush=True)
    except RuntimeError:
        pass  # Already set
else:
    print(f"[Launcher] Windows: Using default spawn method", flush=True)

# Now safe to check the method
print(f"[Launcher] Multiprocessing start method: {mp.get_start_method()}", flush=True)

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Add pc_wrapper to the path FIRST so our modules are imported instead of system ones
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)
sys.path.insert(0, SCRIPT_DIR)

# CRITICAL: Backup stdlib time module BEFORE any patches
# This is needed by fps_calibration.py which needs real time.strftime()
import time as _stdlib_time_backup
sys.modules['_stdlib_time_backup'] = _stdlib_time_backup
print("[Launcher] Backed up stdlib time module as '_stdlib_time_backup'", flush=True)

# CRITICAL: Monkey-patch file operations BEFORE importing any modules
# This redirects /Games/ThumbCommander/ paths to current directory
import builtins

# Patch open()
_original_open = builtins.open
def patched_open(file, mode='r', *args, **kwargs):
    if isinstance(file, str) and file.startswith('/Games/ThumbCommander/'):
        file = file.replace('/Games/ThumbCommander/', '')
    return _original_open(file, mode, *args, **kwargs)
builtins.open = patched_open

# Patch os.stat() (used by cutscene_utils to check if file exists)
# cutscene_utils does: from os import stat
# So we need to patch it in the os module before cutscene_utils is imported
_original_stat = os.stat
def patched_stat(path, *args, **kwargs):
    if isinstance(path, str) and path.startswith('/Games/ThumbCommander/'):
        path = path.replace('/Games/ThumbCommander/', '')
    return _original_stat(path, *args, **kwargs)
os.stat = patched_stat

# Also patch other file operations that might be used
_original_exists = os.path.exists
def patched_exists(path):
    if isinstance(path, str) and path.startswith('/Games/ThumbCommander/'):
        path = path.replace('/Games/ThumbCommander/', '')
    return _original_exists(path)
os.path.exists = patched_exists

# Patch os.listdir() (used by campaign_engine to find campaign files)
_original_listdir = os.listdir
def patched_listdir(path='.'):
    if isinstance(path, str) and path.startswith('/Games/ThumbCommander/'):
        path = path.replace('/Games/ThumbCommander/', '')
        if not path:  # If path becomes empty, use current directory
            path = '.'
    return _original_listdir(path)
os.listdir = patched_listdir

# Import and setup MicroPython compatibility BEFORE any game imports
# Note: micropython_compat automatically installs itself in sys.modules
import pc_wrapper.micropython_compat

# Replace standard modules with our compatibility versions
import pc_wrapper.utime as utime
import pc_wrapper.machine as machine
import pc_wrapper.gc_compat as gc
import pc_wrapper.framebuf as framebuf
import pc_wrapper.engine as engine
import pc_wrapper.engine_io as engine_io
import pc_wrapper.engine_draw as engine_draw
import pc_wrapper.thumbyButton as thumbyButton
import pc_wrapper.thumbyHardware as thumbyHardware
import pc_wrapper._thread as _thread  # Use our multiprocessing-enabled wrapper
import pc_wrapper.audio as audio  # PC-specific audio implementation (no GIL issues!)
# Note: cutscene_utils and thumbycolor_native imported from game directory

# Install modules in sys.modules so they're found by import statements
# micropython is already installed by micropython_compat
sys.modules['utime'] = utime
sys.modules['time'] = utime  # audio.py uses 'import time' and expects ticks_us()
sys.modules['machine'] = machine
sys.modules['gc'] = gc
sys.modules['framebuf'] = framebuf
sys.modules['engine'] = engine
sys.modules['engine_io'] = engine_io
sys.modules['engine_draw'] = engine_draw
sys.modules['_thread'] = _thread
sys.modules['audio'] = audio  # PC-specific audio (bypasses GIL issues!)
# thumbycolor_native will be imported from root directory (original hardware version)
sys.modules['thumbyButton'] = thumbyButton
sys.modules['thumbyHardware'] = thumbyHardware
# cutscene_utils, grayscale, and Intro imported from game directory

# Create a dummy 'lib' directory if it doesn't exist
lib_dir = os.path.join(SCRIPT_DIR, 'lib')
if not os.path.exists(lib_dir):
    os.makedirs(lib_dir)
    # Create dummy font files
    for font_name in ['font3x5.bin', 'font5x7.bin', 'font6x10.bin', 'font8x8.bin']:
        font_path = os.path.join(lib_dir, font_name)
        if not os.path.exists(font_path):
            # Create empty font file
            with open(font_path, 'wb') as f:
                f.write(b'\x00' * 256)


def main():
    """Main entry point"""
    print("=" * 60)
    print("ThumbCommander - ThumbyColor Edition (PC)")
    print("=" * 60)
    print()
    print("Controls:")
    print("  Arrow Keys - Movement")
    print("  Y - Button A (Fire)")
    print("  X - Button B")
    print("  A - Left Bumper")
    print("  S - Right Bumper")
    print("  ESC - Menu")
    print()
    print("Starting game...")
    print("=" * 60)

    # Change to game directory
    os.chdir(SCRIPT_DIR)

    # Set environment variable to force ThumbyColor mode
    os.environ['FORCE_THUMBY_COLOR'] = '1'
    # Set PC mode flag so platform_constants can adjust paths
    os.environ['RUNNING_ON_PC'] = '1'

    # Check if FPS calibration is needed (first run)
    # This must be done BEFORE importing ThumbCommander
    try:
        from pc_wrapper import fps_calibration
        if not os.path.exists(fps_calibration.SETTINGS_FILE):
            print("\n[Launcher] First run detected - running FPS calibration...")
            correction_factor = fps_calibration.get_fps_correction()
            print(f"[Launcher] Calibration complete. Starting game...\n")
    except Exception as e:
        print(f"[Launcher] Warning: FPS calibration failed: {e}")
        print(f"[Launcher] Game will run with default settings")

    # Now import and run the game
    # We need to be careful here because the game modifies sys.path
    try:
        # The game expects to be run from its directory
        # Import the main game module
        import ThumbCommander

        # IMPORTANT: Override the hardcoded path with current directory for PC
        # The game sets loc = "/Games/ThumbCommander/" which doesn't exist on PC
        # We need to fix this after import but the module code already ran...
        # So this needs a different approach - see below
    except Exception as e:
        print(f"Error running game: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
