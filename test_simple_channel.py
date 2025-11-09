#!/usr/bin/env python3
"""
Simple test: Does pygame.mixer.Channel work correctly at 15625 Hz?
No multiprocessing, no threads, just pure pygame.
"""
import pygame
import struct
import time
import math

# Initialize at 15625 Hz
pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()
print(f"Mixer: {pygame.mixer.get_init()}")

# Create channel
channel = pygame.mixer.Channel(0)

# Create test sounds
def make_tone(freq_hz, duration_samples=2048):
    samples = []
    for i in range(duration_samples):
        t = i / 15625.0
        value = int(16000 * math.sin(2 * math.pi * freq_hz * t))
        samples.append(value)
    return pygame.mixer.Sound(buffer=struct.pack('<' + 'h' * len(samples), *samples))

print("\n=== Test: Play and queue 5 chunks ===")
sounds = [make_tone(440 + i*100, 2048) for i in range(5)]

start = time.time()
channel.play(sounds[0])
print(f"T={0:5.0f}ms: Played chunk 0")

for i in range(1, 5):
    time.sleep(0.001)  # 1ms delay
    channel.queue(sounds[i])
    queued = channel.get_queue() is not None
    print(f"T={(time.time()-start)*1000:5.0f}ms: Queued chunk {i}, get_queue()={queued}")

# Monitor channel state
print("\nMonitoring channel (should advance every ~131ms):")
for i in range(20):
    elapsed = (time.time() - start) * 1000
    busy = channel.get_busy()
    queued = channel.get_queue() is not None
    print(f"T={elapsed:6.0f}ms: busy={busy}, queued={queued}")
    if not busy:
        print("  All done!")
        break
    time.sleep(0.050)  # 50ms

pygame.quit()
print("\n=== Test complete ===")
print("If queued stayed True the whole time, pygame.mixer.Channel is BROKEN!")
