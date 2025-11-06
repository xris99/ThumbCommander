#!/usr/bin/env python3
"""Test intro audio loading to verify frequency"""
import sys
import os

# Setup exactly like run_pc.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)
sys.path.insert(0, SCRIPT_DIR)

print("=" * 70)
print("Testing Intro Audio Loading (simulating game startup)")
print("=" * 70)

# Import modules in the same order as the game
print("\n1. Importing engine_draw (initializes pygame)...")
import pc_wrapper.engine_draw
print("   ✓ engine_draw imported")

print("\n2. Importing audio module...")
import pc_wrapper.audio as audio
sys.modules['audio'] = audio
print("   ✓ audio module imported")

print("\n3. Loading intro audio file...")
result = audio.load("intro_128_80.ima")
if result:
    print("   ✓ Intro loaded successfully")

    # Check mixer frequency
    import pygame
    mixer_info = pygame.mixer.get_init()
    if mixer_info:
        freq = mixer_info[0]
        print(f"\n   Mixer frequency: {freq} Hz")
        print(f"   File frequency:  15625 Hz")
        print(f"   Playback speed:  {freq/15625:.2f}x")

        if freq == 15625:
            print("   ⚠️  WARNING: No resampling! Audio will play at original speed")
        elif freq == 12500:
            print("   ✓  CORRECT: Resampling to 12500 Hz (0.80x = slower)")
        elif freq == 11025:
            print("   ⚠️  Using 11025 Hz (0.71x = much slower)")
else:
    print("   ✗ Failed to load intro")

import time
time.sleep(2)
audio.stop()

print("\n" + "=" * 70)
print("Test Complete")
print("=" * 70)
