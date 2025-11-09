#!/usr/bin/env python3
"""
Test consumption with multiprocessing.Queue (not threading.Queue)
This simulates the real scenario more accurately
"""
import multiprocessing as mp
import time
import queue

mp.set_start_method('fork', force=True)

def producer(q, num_samples):
    """Producer process that fills the Queue"""
    print(f"[Producer] Starting, will send {num_samples} samples")
    for i in range(num_samples):
        try:
            q.put_nowait(i)
        except queue.Full:
            print(f"[Producer] Queue full at sample {i}")
            time.sleep(0.01)

    print(f"[Producer] Finished sending {num_samples} samples")

def consumer_with_exact_logic(q, duration=2.0):
    """Consumer using EXACT logic from machine.py _audio_player_thread"""
    print("[Consumer] Starting consumption with exact machine.py logic")

    sample_buffer = []
    consume_count = 0
    last_log = 0
    chunks_played = 0
    chunk_size = 2048

    start_time = time.time()

    while time.time() - start_time < duration:
        # === PHASE 1: CONSUME ALL AVAILABLE SAMPLES ===
        consumed_this_round = 0
        while True:  # Keep consuming until Queue is empty
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

        if consumed_this_round > 0:
            consume_count += consumed_this_round
            if consume_count - last_log >= 5000:
                print(f"[Consumer] Consumed {consume_count} total, buffer: {len(sample_buffer)}", flush=True)
                last_log = consume_count

        # === PHASE 2: PLAYBACK (simulated) ===
        buffer_size = len(sample_buffer)

        # "Play" a chunk if available
        if buffer_size >= chunk_size:
            sample_buffer = sample_buffer[chunk_size:]
            chunks_played += 1
            if chunks_played <= 5 or chunks_played % 10 == 0:
                print(f"[Consumer] Chunk #{chunks_played} played, buffer={len(sample_buffer)}")
        else:
            time.sleep(0.001)  # Wait briefly

    elapsed = time.time() - start_time
    print(f"\n[Consumer] RESULTS:")
    print(f"  Consumed: {consume_count} samples")
    print(f"  Chunks played: {chunks_played}")
    print(f"  Buffer remaining: {len(sample_buffer)}")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Consumption rate: {consume_count/elapsed:.0f} samples/sec")
    print(f"  Required rate: 15625 samples/sec")

    if consume_count/elapsed >= 15625:
        print("  ✓ PASS: Can keep up with decoder!")
    else:
        print("  ✗ FAIL: Cannot keep up with decoder")

if __name__ == '__main__':
    print("Testing multiprocessing.Queue consumption...")
    q = mp.Queue(maxsize=10000)

    # Start producer process
    p = mp.Process(target=producer, args=(q, 15625 * 2))  # 2 seconds worth
    p.start()

    # Let producer get ahead
    time.sleep(0.2)

    # Run consumer in main process
    consumer_with_exact_logic(q, duration=2.5)

    p.join()
    print("\nTest complete!")
