#!/usr/bin/env python3
"""
Minimal test to see if pygame.mixer.Channel works correctly
with 15625 Hz sample rate and real hardware
"""
import pygame
import struct
import time

print("=== Testing pygame.mixer.Channel playback ===\n")

# Initialize pygame mixer with our settings
print("Initializing pygame.mixer...")
pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()
print(f"Mixer initialized: {pygame.mixer.get_init()}\n")

# Create a channel
channel = pygame.mixer.Channel(0)

# Create test sounds (2048 samples each = 131ms at 15625 Hz)
def make_sound(frequency_hz, duration_samples=2048):
    """Create a simple sine wave sound"""
    import math
    samples = []
    for i in range(duration_samples):
        # Generate sine wave at given frequency
        t = i / 15625.0  # time in seconds
        value = int(16000 * math.sin(2 * math.pi * frequency_hz * t))
        samples.append(value)
    audio_bytes = struct.pack('<' + 'h' * len(samples), *samples)
    return pygame.mixer.Sound(buffer=audio_bytes)

print("Creating 3 test sounds (440 Hz, 880 Hz, 1320 Hz)...")
sound1 = make_sound(440, 2048)   # A4 note, 131ms
sound2 = make_sound(880, 2048)   # A5 note, 131ms
sound3 = make_sound(1320, 2048)  # E6 note, 131ms

print("\n--- Test 1: Play + Queue pattern (like our code) ---")
print("T=0ms: Playing sound1...")
start = time.time()
channel.play(sound1)
print(f"  get_busy(): {channel.get_busy()}")
print(f"  get_queue(): {channel.get_queue()}")

print("\nT=1ms: Queuing sound2...")
time.sleep(0.001)
channel.queue(sound2)
print(f"  get_busy(): {channel.get_busy()}")
print(f"  get_queue(): {channel.get_queue() is not None}")

print("\nNow monitoring channel state every 10ms...")
print("Expected: get_queue() should become None after ~131ms when sound2 starts playing\n")

for i in range(30):  # Monitor for 300ms
    elapsed_ms = (time.time() - start) * 1000
    busy = channel.get_busy()
    queued = channel.get_queue() is not None

    print(f"T={elapsed_ms:6.1f}ms: get_busy()={busy}, get_queue()={queued}")

    if not queued and i > 1:
        print(f"\n✓ SUCCESS: sound2 started playing at T={elapsed_ms:.1f}ms")
        break

    time.sleep(0.010)  # 10ms
else:
    print("\n✗ FAILURE: get_queue() never returned False!")
    print("This is exactly the bug we're seeing - channel doesn't advance!")

# Try to queue sound3
print(f"\nTrying to queue sound3...")
time.sleep(0.050)
result = channel.queue(sound3)
print(f"  queue() returned: {result}")
print(f"  get_queue(): {channel.get_queue() is not None}")

# Wait for everything to finish
print("\nWaiting for all sounds to finish...")
time.sleep(0.5)
print(f"Final state: get_busy()={channel.get_busy()}, get_queue()={channel.get_queue()}")

print("\n\n--- Test 2: Rapid queuing (stress test) ---")
print("Creating 10 short sounds and queuing them rapidly...")

short_sounds = [make_sound(440 + i*100, 512) for i in range(10)]  # 32ms each

channel.play(short_sounds[0])
for i in range(1, 10):
    time.sleep(0.001)  # 1ms delay
    channel.queue(short_sounds[i])
    print(f"Queued sound #{i}: get_queue()={channel.get_queue() is not None}")

print("\nIf pygame is working correctly, you should hear a rising tone.")
print("If broken, you'll hear nothing or just the first beep.")

time.sleep(2)

pygame.quit()
print("\n=== Test complete ===")
