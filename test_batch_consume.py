#!/usr/bin/env python3
"""
Test batch consumption from multiprocessing Queue
"""
import multiprocessing as mp
import time
import queue

mp.set_start_method('fork', force=True)

def producer(q):
    """Fill queue with samples at 15625 Hz rate"""
    print("[Producer] Starting")
    sample = 0
    start = time.time()
    target_rate = 15625  # samples per second

    while time.time() - start < 2.0:  # Run for 2 seconds
        try:
            q.put_nowait(sample)
            sample += 1
            # Sleep to maintain target rate
            elapsed = time.time() - start
            expected_samples = int(elapsed * target_rate)
            if sample > expected_samples:
                time.sleep(0.0001)  # Tiny sleep to throttle
        except queue.Full:
            time.sleep(0.001)

    print(f"[Producer] Sent {sample} samples in {time.time()-start:.2f}s")

def consumer_batched(q):
    """Consume in batches like the new code"""
    print("[Consumer] Starting batched consumption")
    consumed = 0
    start = time.time()

    while time.time() - start < 2.5:  # Run a bit longer than producer
        # Consume batch
        batch = []
        try:
            for _ in range(512):
                batch.append(q.get_nowait())
        except queue.Empty:
            pass

        consumed += len(batch)

        if not batch:
            time.sleep(0.001)  # Small sleep if queue empty

    elapsed = time.time() - start
    print(f"[Consumer] Consumed {consumed} samples in {elapsed:.2f}s = {consumed/elapsed:.0f} samples/sec")
    print(f"[Consumer] Required: 15625 samples/sec")
    print(f"[Consumer] Status: {'✓ PASS' if consumed/elapsed >= 15625 else '✗ FAIL'}")

if __name__ == '__main__':
    print("Testing batch consumption with realistic 15625 Hz rate...")
    q = mp.Queue(maxsize=10000)

    p = mp.Process(target=producer, args=(q,))
    p.start()

    time.sleep(0.1)  # Let producer get ahead
    consumer_batched(q)

    p.join()
    print("\nTest complete!")
