#!/usr/bin/env python3
"""
Import test - verifies the game can be imported without errors
This is a quick test before running the full game
"""

import sys
import os

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)
sys.path.insert(0, SCRIPT_DIR)

print("Testing game imports...")
print("=" * 60)

# Setup wrapper
print("\n1. Setting up PC wrapper...")
try:
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

    # Install in sys.modules
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

    print("   ✓ Wrapper modules installed")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Create dummy lib directory
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

# Test platform detection
print("\n3. Testing platform detection...")
try:
    try:
        import engine_io
        IS_THUMBY_COLOR = True
    except ImportError:
        IS_THUMBY_COLOR = False

    print(f"   ✓ Detected as: {'ThumbyColor' if IS_THUMBY_COLOR else 'Thumby'}")
    assert IS_THUMBY_COLOR, "Should detect as ThumbyColor"
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Import platform modules
print("\n4. Importing platform modules...")
try:
    os.chdir(SCRIPT_DIR)
    from platform_constants import get_constants
    PC = get_constants(True)
    print(f"   ✓ Platform constants loaded (Resolution: {PC.WIDTH}x{PC.HEIGHT})")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n5. Importing platform_loader...")
try:
    from platform_loader import display, IS_THUMBY_COLOR, Sprite, PC
    print(f"   ✓ Platform loader imported")
    print(f"   ✓ Display: {type(display).__name__ if display else 'None (pygame not available)'}")
    print(f"   ✓ Sprite: {Sprite.__name__ if Sprite else 'None (pygame not available)'}")
    if not display:
        print("   ⚠ Display not initialized (pygame required)")
        print("   Install pygame to run the game: pip install pygame")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("All import tests passed! ✓")
print("\nThe game should be able to start now.")
print("Run: python run_pc.py")
print("=" * 60)
