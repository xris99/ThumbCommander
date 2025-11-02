#!/usr/bin/env python3
"""
ThumbCommander PC Launcher
Runs the ThumbyColor version of ThumbCommander on PC using pygame

This launcher sets up the MicroPython compatibility layer and launches the game
without modifying any of the game code.
"""

import sys
import os

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Add pc_wrapper to the path FIRST so our modules are imported instead of system ones
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)
sys.path.insert(0, SCRIPT_DIR)

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
import pc_wrapper.audio as audio
# Note: cutscene_utils and thumbycolor_native imported from game directory
import pc_wrapper.grayscale as grayscale
import pc_wrapper.Intro as Intro
import threading as _thread  # Use standard threading as _thread stub

# Install modules in sys.modules so they're found by import statements
# micropython is already installed by micropython_compat
sys.modules['utime'] = utime
sys.modules['machine'] = machine
sys.modules['gc'] = gc
sys.modules['framebuf'] = framebuf
sys.modules['engine'] = engine
sys.modules['engine_io'] = engine_io
sys.modules['engine_draw'] = engine_draw
sys.modules['_thread'] = _thread
# thumbycolor_native will be imported from root directory (original hardware version)
sys.modules['thumbyButton'] = thumbyButton
sys.modules['thumbyHardware'] = thumbyHardware
sys.modules['audio'] = audio
# cutscene_utils will be imported from the game directory
sys.modules['grayscale'] = grayscale
sys.modules['Intro'] = Intro

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
    print("  Z - Button A (Fire)")
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

    # Now import and run the game
    # We need to be careful here because the game modifies sys.path
    try:
        # The game expects to be run from its directory
        # Import the main game module
        import ThumbCommander
    except Exception as e:
        print(f"Error running game: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
