#!/usr/bin/env python3
"""
Test if reinitializing pygame.mixer causes issues
(This is what our code does when switching between audio files)
"""
import pygame
import struct
import time
import math

def make_sound(freq, duration_samples=2048, sample_rate=15625):
    """Create sine wave sound"""
    samples = []
    for i in range(duration_samples):
        t = i / sample_rate
        value = int(16000 * math.sin(2 * math.pi * freq * t))
        samples.append(value)
    audio_bytes = struct.pack('<' + 'h' * len(samples), *samples)
    return pygame.mixer.Sound(buffer=audio_bytes)

print("=== Testing pygame.mixer reinitialization ===\n")

# First initialization (like run_pc.py does)
print("Step 1: Initial init at 16000 Hz (like run_pc.py)")
pygame.mixer.pre_init(frequency=16000, size=-16, channels=1, buffer=512)
pygame.mixer.init()
print(f"  Mixer: {pygame.mixer.get_init()}")

# Reinit to 15625 Hz (like when audio starts)
print("\nStep 2: Quit and reinit to 15625 Hz (like when PWM is created)")
pygame.mixer.quit()
time.sleep(0.05)  # Brief pause like in our code
pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()
print(f"  Mixer: {pygame.mixer.get_init()}")

# Try to play audio
print("\nStep 3: Create channel and play sounds")
channel = pygame.mixer.Channel(0)

sound1 = make_sound(440, 2048)
sound2 = make_sound(880, 2048)

print("  Playing sound1...")
channel.play(sound1)
time.sleep(0.01)

print("  Queuing sound2...")
channel.queue(sound2)

# Monitor
print("\n  Monitoring for 200ms:")
start = time.time()
for i in range(20):
    elapsed_ms = (time.time() - start) * 1000
    busy = channel.get_busy()
    queued = channel.get_queue() is not None
    print(f"    T={elapsed_ms:5.0f}ms: busy={busy}, queued={queued}")
    time.sleep(0.010)

# Test again after another reinit
print("\n\nStep 4: Quit and reinit AGAIN (like loading second audio file)")
pygame.mixer.quit()
time.sleep(0.05)
pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()
print(f"  Mixer: {pygame.mixer.get_init()}")

channel = pygame.mixer.Channel(0)
sound1 = make_sound(440, 2048)
sound2 = make_sound(880, 2048)

print("\n  Playing sound1...")
channel.play(sound1)
time.sleep(0.01)

print("  Queuing sound2...")
channel.queue(sound2)

print("\n  Monitoring for 200ms:")
start = time.time()
for i in range(20):
    elapsed_ms = (time.time() - start) * 1000
    busy = channel.get_busy()
    queued = channel.get_queue() is not None
    print(f"    T={elapsed_ms:5.0f}ms: busy={busy}, queued={queued}")
    time.sleep(0.010)

pygame.quit()
print("\n=== Test complete ===")
print("\nIf get_queue() never becomes False, then reinit is breaking pygame!")
