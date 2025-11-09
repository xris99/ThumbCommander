#!/usr/bin/env python3
"""Quick test of audio playback speed"""
import sys
import os

# Setup path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'pc_wrapper'))
sys.path.insert(0, SCRIPT_DIR)

# Import PC-specific audio
import pc_wrapper.audio as audio
sys.modules['audio'] = audio

print("=" * 60)
print("Audio Speed Test - 11025 Hz")
print("=" * 60)

# Test loading a cutscene file
print("\nTesting intro cutscene (should be 15625 Hz):")
result = audio.load("intro_128_80.ima")
if result:
    print("✓ Loaded successfully")
    print(f"  Playing at 11025 Hz (resampled from 15625 Hz)")
    print(f"  This should play at 11025/15625 = 0.71x speed (slower)")
else:
    print("✗ Failed to load")

import time
time.sleep(3)

audio.stop()
print("\n✓ Test complete")
print("=" * 60)
