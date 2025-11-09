#!/usr/bin/env python3
"""
Test pygame.mixer.Channel.queue() behavior
to understand if there's an issue with our queueing logic
"""
import pygame
import struct
import time
import os

# Use dummy audio driver (no actual sound output)
os.environ['SDL_AUDIODRIVER'] = 'dummy'

# Initialize pygame mixer
pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()

print(f"Mixer initialized: {pygame.mixer.get_init()}")

# Get a channel
channel = pygame.mixer.Channel(0)

print(f"\n=== Testing Channel.queue() behavior ===\n")

# Create some test sounds
def make_sound(sample_value, length=2048):
    """Create a simple sound with constant value"""
    samples = [sample_value] * length
    audio_bytes = struct.pack('<' + 'h' * len(samples), *samples)
    return pygame.mixer.Sound(buffer=audio_bytes)

sound1 = make_sound(5000, 2048)   # 2048 samples = 131ms at 15625 Hz
sound2 = make_sound(10000, 2048)
sound3 = make_sound(15000, 2048)
sound4 = make_sound(20000, 2048)

print("1. Initially, channel should be idle")
print(f"   get_busy(): {channel.get_busy()}")
print(f"   get_queue(): {channel.get_queue()}")

print("\n2. Play sound1")
channel.play(sound1)
print(f"   get_busy(): {channel.get_busy()}")
print(f"   get_queue(): {channel.get_queue()}")
time.sleep(0.01)

print("\n3. Queue sound2 (should work)")
channel.queue(sound2)
print(f"   get_busy(): {channel.get_busy()}")
print(f"   get_queue(): {channel.get_queue()}")

print("\n4. Try to queue sound3 (should fail - only one can be queued)")
try:
    # According to docs, we can only queue one sound
    # But does it raise an error or just return silently?
    result = channel.queue(sound3)
    print(f"   queue() returned: {result}")
    print(f"   get_queue(): {channel.get_queue()}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n5. Wait for sound1 to finish (131ms)")
time.sleep(0.150)  # 150ms to be safe
print(f"   get_busy(): {channel.get_busy()}")
print(f"   get_queue(): {channel.get_queue()}")

print("\n6. Now try to queue sound3 again")
channel.queue(sound3)
print(f"   get_busy(): {channel.get_busy()}")
print(f"   get_queue(): {channel.get_queue()}")

print("\n7. Try to queue sound4 (should fail again)")
result = channel.queue(sound4)
print(f"   queue() returned: {result}")
print(f"   get_queue(): {channel.get_queue()}")

print("\n=== Key Findings ===")
print("- Can only have ONE queued sound at a time")
print("- get_queue() returns None when nothing queued")
print("- get_queue() returns Sound object when something is queued")
print("- CRITICAL: What happens if we call queue() when already have queued sound?")

time.sleep(0.5)
pygame.quit()
