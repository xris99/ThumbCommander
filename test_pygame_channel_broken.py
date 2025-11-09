#!/usr/bin/env python3
"""
Reproduce the EXACT issue: pygame.mixer.Channel.get_queue() never returns None
This test simulates our exact scenario
"""
import pygame
import struct
import time
import math

def make_sound(freq, duration_samples, sample_rate):
    """Create sine wave"""
    samples = []
    for i in range(duration_samples):
        t = i / sample_rate
        value = int(16000 * math.sin(2 * math.pi * freq * t))
        samples.append(value)
    audio_bytes = struct.pack('<' + 'h' * len(samples), *samples)
    return pygame.mixer.Sound(buffer=audio_bytes)

print("=== Reproducing the Channel Stuck Bug ===\n")

# EXACT initialization sequence from our code
print("Step 1: Initialize at 16000 Hz (like run_pc.py)")
pygame.mixer.pre_init(frequency=16000, size=-16, channels=1, buffer=512)
pygame.mixer.init()
print(f"  {pygame.mixer.get_init()}")

print("\nStep 2: Reinitialize to 15625 Hz (like when PWM starts)")
pygame.mixer.quit()
time.sleep(0.05)
pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()
print(f"  {pygame.mixer.get_init()}")

print("\nStep 3: Create channel and play TWO chunks (like our code)")
channel = pygame.mixer.Channel(0)

# Create 2 chunks (2048 samples each, like our code)
chunk1 = make_sound(440, 2048, 15625)
chunk2 = make_sound(880, 2048, 15625)

print("  Playing chunk1 with play()...")
channel.play(chunk1)
print(f"    get_busy()={channel.get_busy()}, get_queue()={channel.get_queue() is not None}")

print("  Queueing chunk2 with queue()...")
time.sleep(0.001)  # 1ms delay like our code
channel.queue(chunk2)
print(f"    get_busy()={channel.get_busy()}, get_queue()={channel.get_queue() is not None}")

print("\nStep 4: Monitor channel state (like our playback thread)")
print("  Expected: get_queue() should become False after ~131ms")
print("  Actual behavior:\n")

start = time.time()
stuck = True

for i in range(300):  # Monitor for 3 seconds
    elapsed_ms = (time.time() - start) * 1000
    busy = channel.get_busy()
    queued = channel.get_queue() is not None

    if i < 20 or i % 10 == 0:
        print(f"    T={elapsed_ms:6.0f}ms: get_busy()={busy:5}, get_queue()={queued:5}")

    if not queued and i > 10:
        print(f"\n  ✓ Channel advanced! Chunk2 started playing at T={elapsed_ms:.0f}ms")
        stuck = False
        break

    time.sleep(0.010)  # 10ms

if stuck:
    print(f"\n  ✗ BUG REPRODUCED: Channel stuck with queued=True for 3+ seconds!")
    print("  This is exactly the bug we're seeing in the logs!")
    print("\n  Trying to stop and restart channel...")
    channel.stop()
    time.sleep(0.050)
    print("  Channel stopped.")

    # Try playing again after stop
    chunk3 = make_sound(660, 2048, 15625)
    print("\n  Playing chunk3 after stop...")
    channel.play(chunk3)
    time.sleep(0.200)

    if channel.get_busy():
        print("  ✓ Audio plays correctly after stop/restart!")
        print("  This confirms: reinit breaks pygame, stop/restart fixes it")
    else:
        print("  ✗ Still broken even after stop")

pygame.quit()
print("\n=== Test Complete ===")
print("\nCONCLUSION:")
print("If get_queue() stayed True for 3+ seconds, this proves:")
print("1. pygame.mixer.quit()/init() breaks Channel playback on macOS")
print("2. The channel thinks it's playing but audio hardware is not advancing")
print("3. This is a pygame/SDL bug with 15625 Hz + reinit on macOS")
