#!/usr/bin/env python3
"""
Test FXEngine functionality with PC-specific audio.py
Tests open_id() and play_id() for pre-loaded sound effects
"""
import sys
import os

# Setup path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)
sys.path.insert(0, SCRIPT_DIR)

# Import PC-specific audio
import pc_wrapper.audio as audio
sys.modules['audio'] = audio

print("=" * 60)
print("FXEngine Test - PC Audio Implementation")
print("=" * 60)

# Change to game directory
os.chdir(SCRIPT_DIR)

# Test 1: Pre-load multiple sound files using open_id
print("\n=== Test 1: Pre-loading sound effects with open_id ===")

sound_files = [
    ("engine.ima", 0),
    ("laser.ima", 1),
    ("shield.ima", 2),
    ("explode_as.ima", 3),
    ("explode_sh.ima", 4),
    ("afterburner.ima", 5),
]

for filename, file_id in sound_files:
    filepath = filename  # Files are in root directory
    if os.path.exists(filepath):
        result = audio.open_id(filepath, file_id)
        print(f"  open_id('{filename}', {file_id}): {'✓ Success' if result >= 0 else '✗ Failed'}")
    else:
        print(f"  ✗ File not found: {filepath}")

# Test 2: Play pre-loaded sounds using play_id
print("\n=== Test 2: Playing pre-loaded sounds with play_id ===")

test_ids = [0, 1, 2]  # Test first 3 sounds
for file_id in test_ids:
    print(f"  play_id({file_id})...", end=" ")
    result = audio.play_id(file_id)
    print("✓ Success" if result else "✗ Failed")

    # Check if playing
    if audio.is_playing():
        print(f"    Audio is playing")

    # Stop immediately (we don't have real audio output in headless mode)
    audio.stop()

# Test 3: Verify API compatibility
print("\n=== Test 3: Verifying FXEngine API compatibility ===")

required_functions = [
    'open_id', 'play_id', 'close_ids', 'stop', 'is_playing',
    'set_loop', 'set_volume', 'set_end_callback', 'clear_end_callback'
]

for func_name in required_functions:
    has_func = hasattr(audio, func_name)
    print(f"  {func_name:20s}: {'✓ Present' if has_func else '✗ Missing'}")

# Test 4: Close all file handles
print("\n=== Test 4: Closing file handles with close_ids ===")
audio.close_ids()
print("  ✓ close_ids() completed")

print("\n" + "=" * 60)
print("FXEngine Test Complete")
print("=" * 60)
