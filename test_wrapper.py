#!/usr/bin/env python3
"""
Test script to verify PC wrapper is working correctly
Run this before running the full game to catch any import errors
"""

import sys
import os

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)
sys.path.insert(0, SCRIPT_DIR)

print("Testing PC Wrapper for ThumbCommander...")
print("=" * 60)

# Test 1: MicroPython compatibility
print("\n1. Testing micropython module...")
try:
    import pc_wrapper.micropython_compat
    from micropython import const, viper, native

    # Test const
    TEST_VALUE = const(42)
    assert TEST_VALUE == 42, "const() should return value unchanged"
    print("   ✓ const() works")

    # Test viper decorator
    @viper
    def test_viper(x: int) -> int:
        return x * 2
    assert test_viper(5) == 10, "viper decorator should work"
    print("   ✓ @viper decorator works")

    # Test native decorator
    @native
    def test_native(x: int) -> int:
        return x + 1
    assert test_native(5) == 6, "native decorator should work"
    print("   ✓ @native decorator works")

except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test 2: Framebuffer
print("\n2. Testing framebuffer module...")
try:
    from framebuf import FrameBuffer, RGB565

    # Create a small framebuffer
    buf = bytearray(10 * 10 * 2)
    fb = FrameBuffer(buf, 10, 10, RGB565)

    # Test fill
    fb.fill(0xFFFF)
    assert fb.pixel(5, 5) == 0xFFFF, "fill() should set all pixels"
    print("   ✓ FrameBuffer fill works")

    # Test pixel
    fb.pixel(5, 5, 0xF800)
    assert fb.pixel(5, 5) == 0xF800, "pixel() should set/get pixels"
    print("   ✓ FrameBuffer pixel works")

    # Test rect
    fb.rect(2, 2, 4, 4, 0x001F, fill=True)
    print("   ✓ FrameBuffer rect works")

except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test 3: Display (requires pygame)
print("\n3. Testing display module...")
try:
    # Check if pygame is available
    import pygame
    import pc_wrapper.thumbycolor_native
    print("   ✓ Display module imports correctly")
    print("   ✓ pygame is installed")

except ImportError as e:
    if 'pygame' in str(e):
        print("   ⚠ pygame not installed (required for display)")
        print("   Run: pip install pygame")
    else:
        print(f"   ✗ FAILED: {e}")
        sys.exit(1)

# Test 4: Button module (requires pygame)
print("\n4. Testing button module...")
try:
    import pygame
    from thumbyButton import ButtonClass

    # Create button
    btn = ButtonClass('A')
    print("   ✓ Button class works")

except ImportError as e:
    if 'pygame' in str(e):
        print("   ⚠ pygame not installed (skipping)")
    else:
        print(f"   ✗ FAILED: {e}")
        sys.exit(1)

# Test 5: Time module
print("\n5. Testing utime module...")
try:
    from utime import ticks_ms, ticks_us, ticks_diff, sleep

    t1 = ticks_ms()
    assert t1 > 0, "ticks_ms should return positive value"
    print("   ✓ ticks_ms works")

    t2 = ticks_us()
    assert t2 > 0, "ticks_us should return positive value"
    print("   ✓ ticks_us works")

    diff = ticks_diff(t2, t1)
    print("   ✓ ticks_diff works")

except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test 6: Other modules
print("\n6. Testing other modules...")
try:
    # Need to setup sys.modules like run_pc.py does
    import pc_wrapper.machine as machine
    import pc_wrapper.gc_compat as gc
    import pc_wrapper.engine as engine
    import pc_wrapper.engine_io as engine_io
    import pc_wrapper.audio as audio
    import pc_wrapper.thumbyHardware as thumbyHardware
    import pc_wrapper.grayscale as grayscale
    import pc_wrapper.cutscene_utils as cutscene_utils

    # Install in sys.modules for game imports
    sys.modules['machine'] = machine
    sys.modules['gc'] = gc
    sys.modules['engine'] = engine
    sys.modules['engine_io'] = engine_io
    sys.modules['audio'] = audio
    sys.modules['thumbyHardware'] = thumbyHardware
    sys.modules['grayscale'] = grayscale
    sys.modules['cutscene_utils'] = cutscene_utils

    print("   ✓ All modules import successfully")

except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Platform detection
print("\n7. Testing platform detection...")
try:
    # The game detects ThumbyColor by trying to import engine_io
    try:
        import engine_io
        IS_THUMBY_COLOR = True
    except ImportError:
        IS_THUMBY_COLOR = False

    assert IS_THUMBY_COLOR == True, "Should detect as ThumbyColor"
    print("   ✓ Platform detection works (detected as ThumbyColor)")

except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("All tests passed! ✓")
print("You can now run: python run_pc.py")
print("=" * 60)
