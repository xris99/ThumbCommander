#!/usr/bin/env python3
"""
Test FPS timing accuracy
Measures actual FPS achieved vs requested FPS
"""

import sys
import time

# Setup PC wrapper
sys.path.insert(0, 'pc_wrapper')
import micropython_compat
import pc_wrapper.utime as utime
import pc_wrapper.engine as engine

sys.modules['time'] = utime
sys.modules['engine'] = engine

def test_fps_timing(target_fps, duration_seconds=5):
    """Test FPS timing for a specific target FPS"""
    print(f"\n{'='*60}")
    print(f"Testing FPS timing: Target = {target_fps} FPS")
    print(f"Expected frame time: {1000.0/target_fps:.3f} ms per frame")
    print(f"Test duration: {duration_seconds} seconds")
    print(f"{'='*60}\n")

    # Set FPS
    engine.fps_limit(target_fps)

    # Reset timing and disable button updates for testing
    import pc_wrapper.engine as eng
    eng._last_tick_time = utime.perf_counter()

    # Disable button updates (we're not testing input)
    original_update_button = eng.update_button_state
    eng.update_button_state = None

    frame_count = 0
    start_time = utime.perf_counter()
    frame_times = []
    last_frame_time = start_time

    print("Frame | Frame Time (ms) | Actual FPS | Cumulative FPS")
    print("-" * 60)

    while (utime.perf_counter() - start_time) < duration_seconds:
        # Simulate display update (busy wait + tick)
        while engine.time_to_next_tick() > 0:
            pass
        engine.tick()

        frame_count += 1
        current_time = utime.perf_counter()

        # Calculate frame time
        frame_time_ms = (current_time - last_frame_time) * 1000.0
        frame_times.append(frame_time_ms)

        # Calculate instantaneous FPS
        instant_fps = 1000.0 / frame_time_ms if frame_time_ms > 0 else 0

        # Calculate cumulative average FPS
        elapsed = current_time - start_time
        cumulative_fps = frame_count / elapsed if elapsed > 0 else 0

        # Print every 10 frames
        if frame_count % 10 == 0:
            print(f"{frame_count:5d} | {frame_time_ms:15.3f} | {instant_fps:10.2f} | {cumulative_fps:14.2f}")

        last_frame_time = current_time

    # Final statistics
    total_time = utime.perf_counter() - start_time
    actual_fps = frame_count / total_time
    avg_frame_time = sum(frame_times) / len(frame_times)
    min_frame_time = min(frame_times)
    max_frame_time = max(frame_times)

    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Target FPS:        {target_fps:.2f}")
    print(f"  Actual FPS:        {actual_fps:.2f}")
    print(f"  FPS Error:         {actual_fps - target_fps:+.2f} ({(actual_fps/target_fps - 1)*100:+.1f}%)")
    print(f"  Total frames:      {frame_count}")
    print(f"  Total time:        {total_time:.3f} seconds")
    print(f"  Avg frame time:    {avg_frame_time:.3f} ms (expected: {1000.0/target_fps:.3f} ms)")
    print(f"  Min frame time:    {min_frame_time:.3f} ms")
    print(f"  Max frame time:    {max_frame_time:.3f} ms")
    print(f"  Frame time jitter: {max_frame_time - min_frame_time:.3f} ms")
    print(f"{'='*60}\n")

    # Restore button updates
    import pc_wrapper.engine as eng
    eng.update_button_state = original_update_button

    # Return error percentage
    return (actual_fps / target_fps - 1) * 100

if __name__ == "__main__":
    print("FPS Timing Test")
    print("===============\n")
    print(f"Using timing method: utime.perf_counter()")
    print(f"Current perf_counter: {utime.perf_counter():.6f}")
    print(f"Has perf_counter: {hasattr(utime, 'perf_counter')}")

    # Test various FPS values
    test_cases = [21, 26, 30, 60]
    errors = {}

    for fps in test_cases:
        error = test_fps_timing(fps, duration_seconds=3)
        errors[fps] = error

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for fps, error in errors.items():
        status = "✓ PASS" if abs(error) < 5 else "✗ FAIL"
        print(f"{fps:3d} FPS: {status:8s} (error: {error:+6.2f}%)")
    print("="*60)
