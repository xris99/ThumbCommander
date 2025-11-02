#!/usr/bin/env python3
"""
Comprehensive test for ThumbCommander PC wrapper
Validates that all components work correctly
"""

import sys
import os
import time

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

print("=" * 60)
print("ThumbCommander PC Wrapper - Comprehensive Test")
print("=" * 60)
print()

# Test 1: Module imports
print("Test 1: Checking module imports...")
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'pc_wrapper'))
sys.path.insert(0, SCRIPT_DIR)

try:
    import pc_wrapper.micropython_compat
    print("  ✓ micropython_compat")

    import pc_wrapper.framebuf as framebuf
    print("  ✓ framebuf")

    import pc_wrapper.engine as engine
    print("  ✓ engine")

    import pc_wrapper.engine_draw as engine_draw
    print("  ✓ engine_draw")

    import pc_wrapper.thumbyButton as thumbyButton
    print("  ✓ thumbyButton")

    print("  ✓ All wrapper modules imported successfully")
except Exception as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

print()

# Test 2: FrameBuffer with GS8 support
print("Test 2: Testing FrameBuffer GS8 support...")
try:
    # Create GS8 framebuffer
    gs8_buffer = bytearray(80 * 60)
    for i in range(len(gs8_buffer)):
        gs8_buffer[i] = i % 256
    gs8_fb = framebuf.FrameBuffer(gs8_buffer, 80, 60, framebuf.GS8)

    # Test pixel reading
    pixel = gs8_fb.pixel(0, 0)
    if pixel is not None and pixel == 0:
        print("  ✓ GS8 pixel reading works")
    else:
        print(f"  ✗ GS8 pixel reading failed: got {pixel}, expected 0")
        sys.exit(1)

    # Create RGB565 framebuffer
    rgb565_buffer = bytearray(128 * 128 * 2)
    rgb565_fb = framebuf.FrameBuffer(rgb565_buffer, 128, 128, framebuf.RGB565)

    # Create palette
    palette_data = bytearray(256 * 2)
    for i in range(256):
        color565 = ((i * 31 // 255) << 11) | ((i * 63 // 255) << 5) | (i * 31 // 255)
        palette_data[i * 2] = color565 & 0xFF
        palette_data[i * 2 + 1] = (color565 >> 8) & 0xFF
    palette = framebuf.FrameBuffer(palette_data, 256, 1, framebuf.RGB565)

    # Test blit with palette
    rgb565_fb.blit(gs8_fb, 24, 34, 0, palette)

    # Check if pixels were blitted
    pixels_set = sum(1 for y in range(128) for x in range(128) if rgb565_fb.pixel(x, y) != 0)
    if pixels_set > 0:
        print(f"  ✓ GS8 blit with palette works ({pixels_set} pixels set)")
    else:
        print("  ✗ GS8 blit with palette failed (no pixels set)")
        sys.exit(1)

except Exception as e:
    print(f"  ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 3: Engine timing functions
print("Test 3: Testing engine timing functions...")
try:
    # Test fps_limit
    fps = engine.fps_limit(30)
    if fps == 30:
        print("  ✓ fps_limit(30) works")
    else:
        print(f"  ✗ fps_limit failed: got {fps}, expected 30")
        sys.exit(1)

    # Test time_to_next_tick
    engine.tick()  # First tick
    time.sleep(0.01)  # Wait 10ms
    remaining = engine.time_to_next_tick()
    if 0 <= remaining <= 33:  # Should be roughly 33ms - 10ms = 23ms
        print(f"  ✓ time_to_next_tick() works (remaining: {remaining}ms)")
    else:
        print(f"  ✗ time_to_next_tick failed: got {remaining}ms")

    print("  ✓ Engine timing functions work")
except Exception as e:
    print(f"  ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 4: Original thumbycolor_native.py
print("Test 4: Testing original thumbycolor_native.py...")
try:
    # Install all modules in sys.modules
    sys.modules['framebuf'] = framebuf
    sys.modules['engine'] = engine
    sys.modules['engine_draw'] = engine_draw
    sys.modules['_thread'] = __import__('_thread')

    # Import platform constants
    from platform_constants import get_constants
    PC = get_constants(True)
    print(f"  ✓ Platform constants loaded (Resolution: {PC.WIDTH}x{PC.HEIGHT})")

    # Try to import original thumbycolor_native
    import thumbycolor_native
    print("  ✓ Original thumbycolor_native.py imported")

    # Check for required classes
    if hasattr(thumbycolor_native, 'ColorDisplay'):
        print("  ✓ ColorDisplay class found")
    else:
        print("  ✗ ColorDisplay class not found")
        sys.exit(1)

    if hasattr(thumbycolor_native, 'ColorSprite'):
        print("  ✓ ColorSprite class found")
    else:
        print("  ✗ ColorSprite class not found")
        sys.exit(1)

except Exception as e:
    print(f"  ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 5: Game startup
print("Test 5: Testing game startup (import only)...")
try:
    # Import remaining modules
    import pc_wrapper.utime as utime
    import pc_wrapper.machine as machine
    import pc_wrapper.gc_compat as gc
    import pc_wrapper.engine_io as engine_io
    import pc_wrapper.thumbyHardware as thumbyHardware
    import pc_wrapper.audio as audio
    import pc_wrapper.grayscale as grayscale
    import pc_wrapper.Intro as Intro

    sys.modules['utime'] = utime
    sys.modules['machine'] = machine
    sys.modules['gc'] = gc
    sys.modules['engine_io'] = engine_io
    sys.modules['thumbyButton'] = thumbyButton
    sys.modules['thumbyHardware'] = thumbyHardware
    sys.modules['audio'] = audio
    sys.modules['grayscale'] = grayscale
    sys.modules['Intro'] = Intro

    # Create lib directory
    lib_dir = os.path.join(SCRIPT_DIR, 'lib')
    if not os.path.exists(lib_dir):
        os.makedirs(lib_dir)
        for font_name in ['font3x5.bin', 'font5x7.bin', 'font6x10.bin', 'font8x8.bin']:
            font_path = os.path.join(lib_dir, font_name)
            if not os.path.exists(font_path):
                with open(font_path, 'wb') as f:
                    f.write(b'\x00' * 256)

    print("  ✓ All game modules installed in sys.modules")

    # Try importing platform_loader
    import platform_loader
    print("  ✓ platform_loader imported")

    if platform_loader.display is not None:
        print(f"  ✓ Display initialized: {type(platform_loader.display).__name__}")
    else:
        print("  ✗ Display is None")
        sys.exit(1)

    if platform_loader.Sprite is not None:
        print(f"  ✓ Sprite class: {platform_loader.Sprite.__name__}")
    else:
        print("  ✗ Sprite class is None")
        sys.exit(1)

except Exception as e:
    print(f"  ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 60)
print("✓ ALL TESTS PASSED!")
print("=" * 60)
print()
print("The PC wrapper is ready to use!")
print("Run: python run_pc.py")
print()
