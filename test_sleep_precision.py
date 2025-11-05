#!/usr/bin/env python3
"""
Test actual sleep precision
"""
import time

print("Testing time.sleep(0.001) precision...")
print("Each sleep should be 1ms, but may be longer due to OS scheduling\n")

total_sleep_requested = 0
total_time_actual = 0

for i in range(100):
    start = time.time()
    time.sleep(0.001)  # Request 1ms sleep
    elapsed = time.time() - start

    total_sleep_requested += 0.001
    total_time_actual += elapsed

    if i < 10 or i % 10 == 0:
        print(f"Sleep #{i}: requested 1.000ms, actual {elapsed*1000:.3f}ms")

print(f"\nTotal requested: {total_sleep_requested*1000:.1f}ms")
print(f"Total actual: {total_time_actual*1000:.1f}ms")
print(f"Overhead: {(total_time_actual - total_sleep_requested)*1000:.1f}ms")
print(f"Average sleep time: {(total_time_actual/100)*1000:.3f}ms")

if total_time_actual > total_sleep_requested * 2:
    print("\n✗ Sleep granularity is TOO COARSE!")
    print("This explains the 21% performance loss!")
else:
    print("\n✓ Sleep precision is reasonable")
