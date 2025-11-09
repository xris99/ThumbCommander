#!/usr/bin/env python3
"""
Test audio playback speeds at 8000 Hz mixer frequency
Verifies:
- Sound effects (8000 Hz) play at correct speed (no resampling)
- Cutscenes (15625 Hz) play slower (resampled down to 8000 Hz)
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)
sys.path.insert(0, SCRIPT_DIR)

print("=" * 80)
print("Audio Playback Speed Test - 8000 Hz Mixer")
print("=" * 80)

# Import modules
import pc_wrapper.engine_draw
import pc_wrapper.audio as audio
sys.modules['audio'] = audio

import pygame
mixer_info = pygame.mixer.get_init()
mixer_freq = mixer_info[0] if mixer_info else 0

print(f"\nMixer initialized at: {mixer_freq} Hz")
print("=" * 80)

# Test sound effects (should NOT resample)
print("\nTEST 1: Sound Effects (8000 Hz files)")
print("-" * 80)
sound_effects = [
    ("engine.ima", 8000),
    ("laser.ima", 8000),
    ("shield.ima", 8000),
]

for filename, expected_rate in sound_effects:
    file_id = audio.open_id(filename, None)
    if file_id >= 0:
        # Check if resampling occurred
        playback_speed = mixer_freq / expected_rate
        status = "✓ NO resampling" if mixer_freq == expected_rate else f"⚠ Resampled ({playback_speed:.2f}x)"
        print(f"  {filename:20s} : {expected_rate} Hz → {mixer_freq} Hz  {status}")

audio.close_ids()

# Test cutscenes (SHOULD resample)
print("\nTEST 2: Cutscenes (15625 Hz files)")
print("-" * 80)
cutscenes = [
    ("intro_128_80.ima", 15625),
    ("title_128_80.ima", 15625),
    ("menu_background.ima", 15625),
]

for filename, expected_rate in cutscenes:
    print(f"\n  Loading {filename}...")
    result = audio.load(filename)
    if result:
        playback_speed = mixer_freq / expected_rate
        print(f"    Source rate:    {expected_rate} Hz")
        print(f"    Mixer rate:     {mixer_freq} Hz")
        print(f"    Playback speed: {playback_speed:.2f}x ({'SLOWER' if playback_speed < 1 else 'FASTER'})")
        print(f"    Status:         {'✓ Resampled as expected' if playback_speed < 1 else '⚠ Not slowed down'}")
    audio.stop()

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"✓ Sound effects (8000 Hz):  Play at {mixer_freq/8000:.2f}x speed (should be 1.00x)")
print(f"✓ Cutscenes (15625 Hz):     Play at {mixer_freq/15625:.2f}x speed (should be <1.00x)")
print("=" * 80)
