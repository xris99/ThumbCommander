#!/usr/bin/env python3
"""
Measure actual cutscene playback with real video rendering
"""

import sys
import os
import time
import struct

os.environ['RUNNING_ON_PC'] = '1'
sys.path.insert(0, 'pc_wrapper')
import micropython_compat

print("="*70)
print("ACTUAL CUTSCENE PLAYBACK MEASUREMENT")
print("="*70)

# Import all necessary modules
import pc_wrapper.audio as audio
from platform_constants import get_constants
from thumbycolor_native import ColorDisplay
import cutscene_utils

# Initialize platform constants
PC = get_constants(is_thumby_color=True)

# Initialize display
display = ColorDisplay()

# Initialize cutscene_utils with required references
def audio_load_wrapper(filename):
    return audio.load(filename)

def audio_play_wrapper():
    audio.play()

def audio_stop_wrapper():
    audio.stop()

# Mock button for cutscene cancel check
class MockButton:
    def pressed(self):
        return False

button_menu = MockButton()

cutscene_utils.init_cutscene_utils(
    display,
    PC,
    audio_load_wrapper,
    audio_play_wrapper,
    audio_stop_wrapper,
    button_menu
)

# Get expected durations
audio_file = "intro_128_80.ima"
video_file = "intro_128_80.COL.bin"

with open(audio_file, 'rb') as f:
    magic = f.read(4)
    sample_rate = struct.unpack('<I', f.read(4))[0]
    sample_count = struct.unpack('<I', f.read(4))[0]
    expected_audio_duration = sample_count / sample_rate

with open(video_file, 'rb') as f:
    magic = f.read(4)
    width, height, frame_count = struct.unpack('<HHH', f.read(6))

fps_21 = 21
fps_26 = 26
expected_video_21fps = frame_count / fps_21
expected_video_26fps = frame_count / fps_26

print(f"\nExpected durations:")
print(f"  Audio: {expected_audio_duration:.3f}s ({sample_count:,} samples @ {sample_rate} Hz)")
print(f"  Video @ 21 FPS: {expected_video_21fps:.3f}s ({frame_count} frames)")
print(f"  Video @ 26 FPS: {expected_video_26fps:.3f}s ({frame_count} frames)")

# === TEST 1: Play cutscene at 21 FPS ===
print("\n" + "="*70)
print("TEST 1: CUTSCENE AT 21 FPS (with audio)")
print("="*70)

print("Playing intro cutscene at 21 FPS...")
print("(Watch the pygame window - this is the actual cutscene rendering)")

start = time.perf_counter()
cutscene_utils.play_cutscene_animation(video_file, fps=21, frame_callback=None)
actual_duration_21fps = time.perf_counter() - start

print(f"\nActual playback time: {actual_duration_21fps:.3f} seconds")
print(f"Expected video time:  {expected_video_21fps:.3f} seconds")
print(f"Expected audio time:  {expected_audio_duration:.3f} seconds")
print(f"Error vs video:       {actual_duration_21fps - expected_video_21fps:+.3f}s ({((actual_duration_21fps/expected_video_21fps)-1)*100:+.2f}%)")

time.sleep(2)

# === TEST 2: Play cutscene at 26 FPS ===
print("\n" + "="*70)
print("TEST 2: CUTSCENE AT 26 FPS (with audio)")
print("="*70)

print("Playing intro cutscene at 26 FPS...")
print("(Watch for sync with audio)")

start = time.perf_counter()
cutscene_utils.play_cutscene_animation(video_file, fps=26, frame_callback=None)
actual_duration_26fps = time.perf_counter() - start

print(f"\nActual playback time: {actual_duration_26fps:.3f} seconds")
print(f"Expected video time:  {expected_video_26fps:.3f} seconds")
print(f"Expected audio time:  {expected_audio_duration:.3f} seconds")
print(f"Error vs video:       {actual_duration_26fps - expected_video_26fps:+.3f}s ({((actual_duration_26fps/expected_video_26fps)-1)*100:+.2f}%)")

# === ANALYSIS ===
print("\n" + "="*70)
print("ANALYSIS")
print("="*70)

print(f"\nActual playback times:")
print(f"  21 FPS: {actual_duration_21fps:.3f}s")
print(f"  26 FPS: {actual_duration_26fps:.3f}s")
print(f"  Audio:  {expected_audio_duration:.3f}s (from file)")

print(f"\nWhich FPS is closer to audio duration?")
diff_21 = abs(actual_duration_21fps - expected_audio_duration)
diff_26 = abs(actual_duration_26fps - expected_audio_duration)

print(f"  21 FPS diff: {diff_21:.3f}s")
print(f"  26 FPS diff: {diff_26:.3f}s")

if diff_21 < diff_26:
    print(f"  → 21 FPS is closer to audio (better sync)")
else:
    print(f"  → 26 FPS is closer to audio (better sync)")

# Calculate actual rendering speed
actual_fps_test1 = frame_count / actual_duration_21fps
actual_fps_test2 = frame_count / actual_duration_26fps

print(f"\nActual achieved FPS:")
print(f"  Test 1 (set to 21): {actual_fps_test1:.2f} FPS")
print(f"  Test 2 (set to 26): {actual_fps_test2:.2f} FPS")

# Determine the issue
print(f"\n" + "="*70)
print("CONCLUSION")
print("="*70)

if actual_fps_test1 < 18:  # Significantly slower than 21
    print("✗ Video rendering is MUCH SLOWER than target FPS")
    print(f"  Set to 21 FPS but only achieving {actual_fps_test1:.1f} FPS")
    print("  This explains why you need to set 26 FPS to actually get ~21 FPS")
elif actual_fps_test1 > 24:  # Much faster
    print("✗ Video rendering is FASTER than target FPS (unexpected)")
else:
    print("✓ Video rendering is close to target FPS")
    print("  The sync issue must be elsewhere")

print("="*70)
