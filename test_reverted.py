#!/usr/bin/env python3
"""Quick test to verify the reverted version works"""
import os
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

print("=== Testing Reverted Version ===\n")

print("1. Testing platform loader...")
try:
    from platform_loader import display, PC, buttonA, IS_THUMBY_COLOR
    print("   ✓ Platform loader imported")
    print(f"   - IS_THUMBY_COLOR: {IS_THUMBY_COLOR}")
    print(f"   - Display type: {type(display).__name__}")
    print(f"   - Button type: {type(buttonA).__name__}")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n2. Testing arrays...")
try:
    from array import array
    test_obj_array = array('O', ['A', 'B', 'C'])
    test_byte_array = array('B', [1, 2, 3])
    print(f"   ✓ Object array: {test_obj_array[0]}, {test_obj_array[1]}, {test_obj_array[2]}")
    print(f"   ✓ Byte array: {test_byte_array[0]}, {test_byte_array[1]}, {test_byte_array[2]}")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n3. Testing ptr32...")
try:
    sintab = array('i', [0, 100, 200, 300])
    v = ptr32(sintab)[1]
    print(f"   ✓ ptr32 works: {v}")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n4. Testing file path redirection...")
try:
    # This should redirect to current directory
    with open('/Games/ThumbCommander/platform_constants.py', 'r') as f:
        first_line = f.readline()
    print(f"   ✓ File path redirection works")
    print(f"   - First line: {first_line.strip()[:50]}...")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n5. Testing display...")
try:
    display.fill(PC.BLACK)
    display.drawText("Test", 10, 10, PC.WHITE)
    display.update()
    print("   ✓ Display rendering works")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n=== All Tests Passed! ===")
