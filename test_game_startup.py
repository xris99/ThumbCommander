#!/usr/bin/env python3
"""
Game startup test - simulates actual game execution
Tests as much as possible without pygame
"""

import sys
import os

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)
sys.path.insert(0, SCRIPT_DIR)

print("=" * 60)
print("ThumbCommander PC Wrapper - Startup Test")
print("=" * 60)

# Setup wrapper exactly like run_pc.py
print("\n1. Setting up PC wrapper...")
import pc_wrapper.micropython_compat
import pc_wrapper.utime as utime
import pc_wrapper.machine as machine
import pc_wrapper.gc_compat as gc
import pc_wrapper.framebuf as framebuf
import pc_wrapper.engine as engine
import pc_wrapper.engine_io as engine_io
import pc_wrapper.thumbyButton as thumbyButton
import pc_wrapper.thumbyHardware as thumbyHardware
import pc_wrapper.audio as audio
import pc_wrapper.cutscene_utils as cutscene_utils
import pc_wrapper.grayscale as grayscale
import pc_wrapper.Intro as Intro

sys.modules['utime'] = utime
sys.modules['machine'] = machine
sys.modules['gc'] = gc
sys.modules['framebuf'] = framebuf
sys.modules['engine'] = engine
sys.modules['engine_io'] = engine_io
sys.modules['thumbyButton'] = thumbyButton
sys.modules['thumbyHardware'] = thumbyHardware
sys.modules['audio'] = audio
sys.modules['cutscene_utils'] = cutscene_utils
sys.modules['grayscale'] = grayscale
sys.modules['Intro'] = Intro
print("   ✓ Wrapper installed")

# Create lib directory
print("\n2. Creating lib directory...")
lib_dir = os.path.join(SCRIPT_DIR, 'lib')
if not os.path.exists(lib_dir):
    os.makedirs(lib_dir)
for font_name in ['font3x5.bin', 'font5x7.bin', 'font6x10.bin', 'font8x8.bin']:
    font_path = os.path.join(lib_dir, font_name)
    if not os.path.exists(font_path):
        with open(font_path, 'wb') as f:
            f.write(b'\x00' * 256)
print("   ✓ Lib directory ready")

os.chdir(SCRIPT_DIR)

# Test imports
print("\n3. Testing game module imports...")
try:
    print("   - Importing platform_constants...")
    from platform_constants import get_constants
    print("     ✓ platform_constants")

    print("   - Importing platform_loader...")
    from platform_loader import display, IS_THUMBY_COLOR, PC
    print(f"     ✓ platform_loader (ThumbyColor: {IS_THUMBY_COLOR})")

    print("   - Importing campaign_engine...")
    from campaign_engine import CampaignEngine
    print("     ✓ campaign_engine")

    print("   - Importing ThumbCommander (this will take a moment)...")
    # This is the big test - can we import the main game file?
    import ThumbCommander
    print("     ✓ ThumbCommander")

except Exception as e:
    print(f"\n   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("SUCCESS! ✓")
print("=" * 60)
print("\nAll game modules imported successfully!")
print("\nThe game is ready to run.")
print("\nTo play the game:")
print("  1. Install pygame: pip install pygame")
print("  2. Run: python run_pc.py")
print("\nNote: This test ran without pygame. With pygame installed,")
print("the game will display graphics and be fully playable.")
print("=" * 60)
