#!/usr/bin/env python3
"""
Test multiprocessing Queue consumption speed
"""
import multiprocessing as mp
import time
import queue

# Force fork method
mp.set_start_method('fork', force=True)

def producer(q, num_samples):
    """Producer sends samples to queue"""
    print(f"[Producer] Starting, will send {num_samples} samples")
    start = time.time()

    for i in range(num_samples):
        try:
            q.put_nowait(i)
        except queue.Full:
            print(f"[Producer] Queue full at {i}")
            break

    elapsed = time.time() - start
    print(f"[Producer] Sent {num_samples} samples in {elapsed:.3f}s = {num_samples/elapsed:.0f} samples/sec")

def consumer_slow(q, num_samples):
    """Consumer gets ONE sample at a time (slow!)"""
    print(f"[Consumer SLOW] Starting, will consume {num_samples} samples")
    start = time.time()

    consumed = 0
    while consumed < num_samples:
        try:
            val = q.get(timeout=0.01)
            consumed += 1
        except queue.Empty:
            break

    elapsed = time.time() - start
    print(f"[Consumer SLOW] Consumed {consumed} samples in {elapsed:.3f}s = {consumed/elapsed:.0f} samples/sec")

def consumer_fast(q, num_samples):
    """Consumer gets in batches (fast!)"""
    print(f"[Consumer FAST] Starting, will consume {num_samples} samples")
    start = time.time()

    consumed = 0
    batch = []
    while consumed < num_samples:
        try:
            # Get as many as possible without blocking
            while len(batch) < 1000:
                batch.append(q.get_nowait())
            consumed += len(batch)
            batch = []
        except queue.Empty:
            if batch:
                consumed += len(batch)
                batch = []
            time.sleep(0.001)

    elapsed = time.time() - start
    print(f"[Consumer FAST] Consumed {consumed} samples in {elapsed:.3f}s = {consumed/elapsed:.0f} samples/sec")

if __name__ == '__main__':
    num_samples = 15625  # 1 second of audio

    print("\n=== Test 1: Slow consumption (one at a time) ===")
    q = mp.Queue(maxsize=10000)
    p = mp.Process(target=producer, args=(q, num_samples))
    p.start()
    time.sleep(0.1)  # Let producer fill queue
    consumer_slow(q, num_samples)
    p.join()

    print("\n=== Test 2: Fast consumption (batched) ===")
    q = mp.Queue(maxsize=10000)
    p = mp.Process(target=producer, args=(q, num_samples))
    p.start()
    time.sleep(0.1)  # Let producer fill queue
    consumer_fast(q, num_samples)
    p.join()

    print("\nRequired speed: 15625 samples/sec")
    print("If slow consumer < 15625, it can't keep up!")
