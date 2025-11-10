#!/usr/bin/env python3
"""
Measure actual playback duration of intro video and audio
"""

import sys
import os
import time
import struct

os.environ['RUNNING_ON_PC'] = '1'
sys.path.insert(0, 'pc_wrapper')
import micropython_compat

print("="*70)
print("PLAYBACK TIMING MEASUREMENT")
print("="*70)

# === TEST 1: Audio Playback Duration ===
print("\n" + "="*70)
print("TEST 1: AUDIO PLAYBACK")
print("="*70)

import pc_wrapper.audio as audio

audio_file = "intro_128_80.ima"

with open(audio_file, 'rb') as f:
    magic = f.read(4)
    sample_rate = struct.unpack('<I', f.read(4))[0]
    sample_count = struct.unpack('<I', f.read(4))[0]
    expected_audio_duration = sample_count / sample_rate

print(f"Audio: {sample_count:,} samples at {sample_rate} Hz")
print(f"Expected duration: {expected_audio_duration:.3f} seconds")
print(f"\nPlaying audio and measuring...")

start = time.perf_counter()
audio.load(audio_file)
audio.play()

while audio.is_playing():
    time.sleep(0.01)

actual_audio_duration = time.perf_counter() - start
audio.stop()

print(f"Actual duration:   {actual_audio_duration:.3f} seconds")
print(f"Error: {actual_audio_duration - expected_audio_duration:+.3f} s ({((actual_audio_duration/expected_audio_duration)-1)*100:+.2f}%)")

# === TEST 2: Video Playback Duration ===
print("\n" + "="*70)
print("TEST 2: VIDEO PLAYBACK SIMULATION")
print("="*70)

import pc_wrapper.engine as engine
import pc_wrapper.utime as utime

video_file = "intro_128_80.COL.bin"

with open(video_file, 'rb') as f:
    magic = f.read(4)
    width, height, frame_count = struct.unpack('<HHH', f.read(6))

fps = 21
expected_video_duration = frame_count / fps

print(f"Video: {frame_count} frames at {fps} FPS")
print(f"Expected duration: {expected_video_duration:.3f} seconds")
print(f"\nSimulating video playback...")

engine.fps_limit(fps)

# Disable button updates for test
import pc_wrapper.engine as eng
eng._last_tick_time = utime.perf_counter()
original_update_button = eng.update_button_state
eng.update_button_state = None

start = time.perf_counter()

for frame_idx in range(frame_count):
    while engine.time_to_next_tick() > 0:
        pass
    engine.tick()

actual_video_duration = time.perf_counter() - start

# Restore
eng.update_button_state = original_update_button

print(f"Actual duration:   {actual_video_duration:.3f} seconds")
print(f"Actual FPS:        {frame_count / actual_video_duration:.2f}")
print(f"Error: {actual_video_duration - expected_video_duration:+.3f} s ({((actual_video_duration/expected_video_duration)-1)*100:+.2f}%)")

# === ANALYSIS ===
print("\n" + "="*70)
print("SYNC ANALYSIS")
print("="*70)

print(f"\nExpected durations at nominal rates:")
print(f"  Audio:  {expected_audio_duration:.3f} s (at {sample_rate} Hz)")
print(f"  Video:  {expected_video_duration:.3f} s (at {fps} FPS)")
print(f"  Mismatch: {expected_audio_duration - expected_video_duration:+.3f} s ({((expected_audio_duration/expected_video_duration)-1)*100:+.1f}%)")

print(f"\nActual measured playback durations:")
print(f"  Audio:  {actual_audio_duration:.3f} s")
print(f"  Video:  {actual_video_duration:.3f} s")
print(f"  Mismatch: {actual_audio_duration - actual_video_duration:+.3f} s ({((actual_audio_duration/actual_video_duration)-1)*100:+.1f}%)")

# Calculate what's wrong
audio_speed_ratio = expected_audio_duration / actual_audio_duration
video_speed_ratio = expected_video_duration / actual_video_duration

print(f"\nPlayback speed analysis:")
print(f"  Audio speed:  {audio_speed_ratio:.4f}x (1.0 = correct)")
print(f"  Video speed:  {video_speed_ratio:.4f}x (1.0 = correct)")

if audio_speed_ratio < 0.95:
    print(f"  ⚠️  Audio is playing TOO FAST ({(1-audio_speed_ratio)*100:.1f}% too fast)")
elif audio_speed_ratio > 1.05:
    print(f"  ⚠️  Audio is playing TOO SLOW ({(audio_speed_ratio-1)*100:.1f}% too slow)")
else:
    print(f"  ✓  Audio speed is acceptable")

if video_speed_ratio < 0.95:
    print(f"  ⚠️  Video is playing TOO FAST ({(1-video_speed_ratio)*100:.1f}% too fast)")
elif video_speed_ratio > 1.05:
    print(f"  ⚠️  Video is playing TOO SLOW ({(video_speed_ratio-1)*100:.1f}% too slow)")
else:
    print(f"  ✓  Video speed is acceptable")

# Calculate required FPS for sync
if actual_audio_duration > 0:
    required_fps_for_sync = frame_count / actual_audio_duration
    print(f"\nRequired video FPS to sync with audio: {required_fps_for_sync:.2f}")
    print(f"Current FPS: {fps}")
    print(f"User reports needing: 26 FPS")

print("="*70)
