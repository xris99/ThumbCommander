#!/usr/bin/env python3
"""
Full end-to-end test of the audio pipeline:
- Producer process sends samples to Queue (like decoder)
- Consumer thread uses pygame.mixer.Channel (like playback thread)
- Tests if we can sustain 15625 samples/sec
"""
import multiprocessing as mp
import threading
import time
import queue
import pygame
import struct
import os

mp.set_start_method('fork', force=True)
os.environ['SDL_AUDIODRIVER'] = 'dummy'

# Initialize pygame
pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
pygame.mixer.init()

def producer(q, duration=2.0):
    """Producer process: sends samples at 15625 Hz (like audio decoder)"""
    print(f"[Producer] Starting, will produce for {duration}s")
    sample = 0
    start = time.time()
    target_rate = 15625

    samples_sent = 0
    samples_dropped = 0

    while time.time() - start < duration:
        try:
            q.put_nowait(sample)
            samples_sent += 1
        except queue.Full:
            samples_dropped += 1
            if samples_dropped % 1000 == 0:
                print(f"[Producer] Queue full, dropped {samples_dropped} samples")

        sample += 1

        # Sleep to maintain target rate (simple rate limiting)
        expected_time = start + (sample / target_rate)
        sleep_time = expected_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

    elapsed = time.time() - start
    print(f"[Producer] Finished: sent {samples_sent}, dropped {samples_dropped} in {elapsed:.2f}s")

def consumer_exact_logic(q, duration=2.5):
    """Consumer using EXACT logic from machine.py"""
    print("[Consumer] Starting with exact machine.py playback logic")

    chunk_size = 2048
    chunks_played = 0
    playback_started = False
    sample_buffer = []
    consume_count = 0
    last_log = 0

    # Get pygame channel
    channel = pygame.mixer.Channel(0)

    start_time = time.time()

    # Main loop: matches _audio_player_thread exactly
    while time.time() - start_time < duration:
        # === PHASE 1: CONSUME ALL AVAILABLE SAMPLES ===
        consumed_this_round = 0
        while True:  # Keep consuming until Queue is empty
            batch = []
            try:
                for _ in range(1024):
                    batch.append(q.get_nowait())
            except queue.Empty:
                pass

            if batch:
                sample_buffer.extend(batch)
                consumed_this_round += len(batch)
            else:
                break  # Queue is empty

        if consumed_this_round > 0:
            consume_count += consumed_this_round
            if consume_count - last_log >= 5000:
                print(f"[Consumer] Consumed {consume_count} total, buffer: {len(sample_buffer)}", flush=True)
                last_log = consume_count

        # === PHASE 2: PLAYBACK ===
        buffer_size = len(sample_buffer)

        # Start playback as soon as we have one chunk
        if not playback_started:
            if buffer_size >= chunk_size:
                playback_started = True
                print(f"[Consumer] Starting playback with {buffer_size} samples buffered", flush=True)
            else:
                time.sleep(0.001)
                continue

        # Check if pygame is ready for next chunk
        queued = channel.get_queue()
        if queued is not None:
            # Debug: log if stuck waiting
            if chunks_played >= 4 and chunks_played <= 6:
                elapsed_ms = (time.time() - start_time) * 1000
                print(f"[Consumer] T={elapsed_ms:.0f}ms: Waiting for queue slot (chunks_played={chunks_played}, get_queue()={queued is not None})")
            time.sleep(0.001)
            continue

        # Extract chunk if available
        if buffer_size >= chunk_size:
            chunk = sample_buffer[:chunk_size]
            sample_buffer = sample_buffer[chunk_size:]

            chunks_played += 1

            try:
                # Convert to signed 16-bit PCM (same as machine.py)
                signed_samples = [max(-32768, min(32767, int(s) - 32768)) for s in chunk]
                audio_bytes = struct.pack('<' + 'h' * len(signed_samples), *signed_samples)
                sound = pygame.mixer.Sound(buffer=audio_bytes)

                # First chunk uses play(), rest use queue()
                if chunks_played == 1:
                    channel.play(sound)
                else:
                    channel.queue(sound)

                if chunks_played <= 5 or chunks_played % 10 == 0:
                    print(f"[Consumer] Chunk #{chunks_played} queued, buffer={len(sample_buffer)}")

            except Exception as e:
                print(f"[Consumer] ERROR: {e}")
                break
        else:
            time.sleep(0.001)

    elapsed = time.time() - start_time
    print(f"\n=== CONSUMER RESULTS ===")
    print(f"  Consumed: {consume_count} samples")
    print(f"  Chunks played: {chunks_played}")
    print(f"  Buffer remaining: {len(sample_buffer)}")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Consumption rate: {consume_count/elapsed:.0f} samples/sec")
    print(f"  Playback rate: {chunks_played * chunk_size / elapsed:.0f} samples/sec")
    print(f"  Required rate: 15625 samples/sec")

    if consume_count/elapsed >= 15625 and chunks_played * chunk_size / elapsed >= 15000:
        print("  ✓ PASS: Audio pipeline works!")
    else:
        print("  ✗ FAIL: Cannot sustain required rate")

    return consume_count, chunks_played

if __name__ == '__main__':
    print("=== Full Audio Pipeline Test ===\n")

    # Create Queue
    q = mp.Queue(maxsize=10000)

    # Start producer process (like audio decoder)
    p = mp.Process(target=producer, args=(q, 2.0))
    p.start()

    # Small delay to let producer get ahead
    time.sleep(0.1)

    # Run consumer in main process (like playback thread)
    consumed, chunks = consumer_exact_logic(q, duration=2.5)

    # Wait for producer to finish
    p.join()

    print("\n=== Test Complete ===")
    pygame.quit()
