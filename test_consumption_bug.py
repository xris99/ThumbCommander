#!/usr/bin/env python3
"""
Test to identify the consumption bug
Simulates the exact consumption loop logic from machine.py
"""
import queue
import time

def test_consumption_loop():
    """Test the consumption loop logic"""
    # Create a queue with 10,000 samples
    q = queue.Queue(maxsize=15000)

    # Fill it with samples
    print("Filling queue with 10,000 samples...")
    for i in range(10000):
        q.put(i)

    print(f"Queue size: {q.qsize()}")

    # Now test the consumption loop (EXACT code from machine.py)
    sample_buffer = []
    consume_count = 0
    iteration = 0

    print("\nStarting consumption loop...")
    start_time = time.time()

    while iteration < 20:  # Limit iterations for testing
        iteration += 1

        # === PHASE 1: CONSUME ALL AVAILABLE SAMPLES ===
        consumed_this_round = 0
        inner_iterations = 0

        while True:  # Keep consuming until Queue is empty
            inner_iterations += 1
            batch = []
            try:
                # Get up to 1024 samples in one batch
                for _ in range(1024):
                    batch.append(q.get_nowait())
            except queue.Empty:
                pass  # No more samples available

            if batch:
                sample_buffer.extend(batch)
                consumed_this_round += len(batch)
            else:
                break  # Queue is empty, move to playback phase

        consume_count += consumed_this_round

        if consumed_this_round > 0:
            print(f"Iter {iteration}: inner_iters={inner_iterations}, consumed={consumed_this_round}, total={consume_count}, buffer={len(sample_buffer)}, queue={q.qsize()}")

        # === PHASE 2: PLAYBACK (simulate) ===
        # Remove one chunk from buffer
        if len(sample_buffer) >= 2048:
            sample_buffer = sample_buffer[2048:]
            # print(f"  Played chunk, buffer now {len(sample_buffer)}")

        # Small delay to simulate playback timing
        time.sleep(0.001)

        # If queue is empty and buffer is empty, we're done
        if q.qsize() == 0 and len(sample_buffer) == 0:
            break

    elapsed = time.time() - start_time

    print(f"\n=== RESULTS ===")
    print(f"Total consumed: {consume_count}")
    print(f"Final buffer size: {len(sample_buffer)}")
    print(f"Final queue size: {q.qsize()}")
    print(f"Time elapsed: {elapsed:.3f}s")
    print(f"Expected: All 10,000 samples consumed")

    if consume_count == 10000 and q.qsize() == 0:
        print("✓ PASS: Consumption loop works correctly!")
    else:
        print("✗ FAIL: Consumption loop has a bug!")

if __name__ == '__main__':
    test_consumption_loop()
