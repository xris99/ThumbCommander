#!/usr/bin/env python3
"""
Test if pygame.mixer.Channel.get_queue() is slow/blocking
This could explain why the playback thread is so slow!
"""
import pygame
import time
import struct
import math

pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()

channel = pygame.mixer.Channel(0)

# Create test sound
def make_sound(freq, samples=2048):
    data = [int(16000 * math.sin(2 * math.pi * freq * i / 15625)) for i in range(samples)]
    return pygame.mixer.Sound(buffer=struct.pack('<' + 'h' * len(data), *data))

sound1 = make_sound(440, 2048)
sound2 = make_sound(880, 2048)

print("=== Testing get_queue() performance ===\n")

# Test 1: How long does get_queue() take?
print("Test 1: Measure get_queue() call time")
channel.play(sound1)
time.sleep(0.01)
channel.queue(sound2)

times = []
for i in range(1000):
    start = time.perf_counter()
    result = channel.get_queue()
    elapsed = time.perf_counter() - start
    times.append(elapsed * 1000000)  # microseconds

avg_time = sum(times) / len(times)
max_time = max(times)
print(f"  Average: {avg_time:.2f} µs")
print(f"  Max: {max_time:.2f} µs")

if avg_time > 100:
    print(f"  ✗ WARNING: get_queue() is VERY SLOW! ({avg_time:.0f}µs average)")
    print(f"     At 0.1ms loop time, we can only call it ~{100/avg_time:.1f} times!")
else:
    print(f"  ✓ get_queue() is fast enough")

# Test 2: How many get_queue() calls per second?
print("\nTest 2: How many get_queue() calls in 1 second?")
start = time.time()
count = 0
while time.time() - start < 1.0:
    _ = channel.get_queue()
    count += 1

print(f"  Calls per second: {count:,}")
print(f"  Time per call: {1000000/count:.2f} µs")

if count < 10000:
    print(f"  ✗ WARNING: Only {count} calls/sec is TOO SLOW!")
    print(f"     We need ~10,000 calls/sec to keep up with audio")
else:
    print(f"  ✓ Fast enough for real-time audio")

# Test 3: Does it block when channel is busy?
print("\nTest 3: Does get_queue() block when channel is busy?")
channel.stop()
time.sleep(0.1)

channel.play(sound1)
channel.queue(sound2)

print("  Calling get_queue() 100 times while channel is busy...")
start = time.time()
for i in range(100):
    _ = channel.get_queue()
elapsed = time.time() - start

print(f"  Total time: {elapsed*1000:.2f} ms")
print(f"  Per call: {elapsed*10:.2f} ms")

if elapsed > 0.1:  # More than 1ms per call
    print(f"  ✗ BLOCKING DETECTED! get_queue() takes {elapsed*10:.1f}ms per call!")
    print(f"     This would destroy real-time audio performance")
else:
    print(f"  ✓ No blocking detected")

pygame.quit()

print("\n=== CONCLUSION ===")
print("If get_queue() is slow (>100µs) or blocking, this explains")
print("why the playback thread can't keep up with the decoder!")
