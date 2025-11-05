#!/usr/bin/env python3
"""
Test if dummy audio driver actually advances playback
or if sounds get stuck in queue forever
"""
import pygame
import struct
import time
import os

os.environ['SDL_AUDIODRIVER'] = 'dummy'

pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()

print(f"Mixer initialized: {pygame.mixer.get_init()}")

channel = pygame.mixer.Channel(0)

def make_sound(value, length=2048):
    samples = [value] * length
    audio_bytes = struct.pack('<' + 'h' * len(samples), *samples)
    return pygame.mixer.Sound(buffer=audio_bytes)

sound1 = make_sound(5000, 2048)
sound2 = make_sound(10000, 2048)
sound3 = make_sound(15000, 2048)

print("\n=== Testing if dummy driver actually plays sounds ===\n")

print("T=0ms: Play sound1 (2048 samples @ 15625 Hz = 131ms duration)")
start = time.time()
channel.play(sound1)
print(f"  get_busy(): {channel.get_busy()}")
print(f"  get_queue(): {channel.get_queue()}")

print("\nT=1ms: Queue sound2")
time.sleep(0.001)
channel.queue(sound2)
print(f"  get_busy(): {channel.get_busy()}")
print(f"  get_queue(): {channel.get_queue()}")

# Now wait and check every 50ms to see when sound2 starts playing
print("\nWaiting for sound1 to finish and sound2 to start...")
print("Expected: sound2 should start at T=131ms")
print("If get_queue() never returns None, dummy driver is broken!\n")

for i in range(20):  # Check for 1 second total
    elapsed_ms = (time.time() - start) * 1000
    busy = channel.get_busy()
    queued = channel.get_queue()

    print(f"T={elapsed_ms:6.1f}ms: get_busy()={busy:5}, get_queue()={'Sound' if queued else 'None ':5}")

    if queued is None and i > 2:
        print(f"\n✓ SUCCESS: get_queue() returned None at T={elapsed_ms:.1f}ms")
        print("This means sound2 started playing (no longer queued)")
        break

    time.sleep(0.050)  # 50ms
else:
    print(f"\n✗ FAILURE: get_queue() NEVER returned None!")
    print("Dummy driver may not actually play sounds")
    print("This would cause an infinite loop in our playback thread!")

print("\nFinal check:")
time.sleep(0.2)  # Wait a bit more
print(f"  get_busy(): {channel.get_busy()}")
print(f"  get_queue(): {channel.get_queue()}")

pygame.quit()
