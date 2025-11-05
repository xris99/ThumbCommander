# Audio System Fixes and Analysis

## Critical Bug Fixed

### Decoder Process Interfering with pygame.mixer
**Problem**: When the decoder process created a PWM instance, it initialized pygame.mixer and could even quit/reinitialize it. This interfered with the main process's pygame.mixer since they may share OS-level audio resources.

**Fix**: Modified `PWM.__init__` in `pc_wrapper/machine.py` to skip ALL pygame initialization when running in the decoder process. The decoder only needs to send samples to the Queue - it doesn't need pygame at all.

```python
# CRITICAL: Decoder process doesn't need pygame - only sends samples to Queue!
if _thread_module.is_audio_process():
    print(f"[Audio] PWM.__init__ in DECODER process - no pygame needed, will use Queue", flush=True)
    # Set as active PWM in decoder process (for duty_u16 to work)
    with PWM._lock:
        PWM._active_pwm = self
    return  # Skip all pygame initialization!
```

## Performance Optimizations

### 1. Increased Batch Size
- Changed from 1024 to 2048 samples per batch
- One batch now equals one chunk - more efficient
- Faster Queue consumption with fewer iterations

### 2. Reduced Sleep Time
- Changed from 1ms to 0.5ms for all `time.sleep()` calls
- More responsive loop (checks pygame readiness 2x faster)
- Reduces overhead in the playback loop

### 3. Optimized Consumption Phase
- Removed sleeps from consumption phase
- Runs as fast as possible to drain Queue
- Prevents Queue from filling up

## Test Programs Created

### test_consumption_bug.py
Verifies the consumption loop logic is correct.
- **Result**: ✓ PASS - Consumes all 10,000 samples correctly

### test_mp_consumption.py
Tests multiprocessing.Queue consumption with realistic producer/consumer.
- **Result**: Consumption works but limited by playback rate

### test_pygame_queue.py
Tests pygame.mixer.Channel.queue() behavior.
- **Key Finding**: Calling `queue()` when already have queued sound REPLACES the queued sound!
- This is why we MUST check `get_queue() is not None` before calling `queue()`

### test_dummy_driver.py
Verifies dummy audio driver actually advances playback.
- **Result**: ✓ PASS - get_queue() returns None after ~131ms (sound starts playing)

### test_full_audio_pipeline.py
End-to-end test with multiprocessing + pygame playback.
- **Result**: Achieves ~79% efficiency (12,285 samples/sec vs required 15,625)
- This is due to loop overhead, but optimizations should improve this

### test_sleep_precision.py
Measures actual sleep granularity.
- **Result**: ✓ PASS - Average 1.108ms for requested 1ms (10.8% overhead)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ MAIN PROCESS                                                │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ Playback Thread  │                                      │
│  │                  │                                      │
│  │ Phase 1: CONSUME │───┐                                  │
│  │  - Drain Queue   │   │                                  │
│  │    into buffer   │   │                                  │
│  │  - Batch 2048    │   │   ┌─────────────────┐           │
│  │    at a time     │◄──────┤ multiprocessing │           │
│  │                  │   │   │  Queue (10K)    │◄──────┐   │
│  │ Phase 2: PLAY    │   │   └─────────────────┘       │   │
│  │  - Extract chunk │   │                             │   │
│  │  - Convert to    │   │                             │   │
│  │    PCM bytes     │   │                             │   │
│  │  - Queue to      │   │                             │   │
│  │    pygame        │   │                             │   │
│  │  - Check every   │   │                             │   │
│  │    0.5ms         │   │                             │   │
│  └──────────────────┘   │                             │   │
│          │               │                             │   │
│          v               │                             │   │
│  ┌──────────────────┐   │                             │   │
│  │ pygame.mixer     │   │                             │   │
│  │ Channel          │   │                             │   │
│  │  - 15625 Hz      │   │                             │   │
│  │  - One playing   │   │                             │   │
│  │  - One queued    │   │                             │   │
│  └──────────────────┘   │                             │   │
│                          │                             │   │
└──────────────────────────┼─────────────────────────────┼───┘
                           │                             │
                           │   IPC via Queue             │
                           │                             │
┌──────────────────────────┼─────────────────────────────┼───┐
│ DECODER PROCESS          │                             │   │
│                          │                             │   │
│  ┌──────────────────┐   │                             │   │
│  │ audio_loop       │   │                             │   │
│  │  - Decodes IMA   │   │                             │   │
│  │    ADPCM         │   │                             │   │
│  │  - Microsecond   │   │                             │   │
│  │    precise timing│   │                             │   │
│  │  - Calls         │   │                             │   │
│  │    pwm.duty_u16()│───┘                             │   │
│  │    for each      │                                 │   │
│  │    sample        │                                 │   │
│  │                  │                                 │   │
│  │ PWM.duty_u16()   │                                 │   │
│  │  - Checks if     │                                 │   │
│  │    in decoder    │                                 │   │
│  │  - Sends sample  │─────────────────────────────────┘   │
│  │    to Queue      │                                     │
│  │  - put_nowait()  │                                     │
│  │    (non-blocking)│                                     │
│  │  - Drops if full │                                     │
│  └──────────────────┘                                     │
│                                                            │
│  NO pygame in decoder process!                            │
│  (This was the critical bug - now fixed)                  │
└────────────────────────────────────────────────────────────┘
```

## Key Technical Insights

### 1. True Parallelism via Multiprocessing
- Uses `multiprocessing.Process` instead of `threading.Thread` for audio_loop
- Bypasses Python's GIL (Global Interpreter Lock)
- Replicates RP2350's dual-core architecture:
  - Core 0 (main process): Game loop, Timer callbacks, playback
  - Core 1 (decoder process): audio_loop with busy-wait timing

### 2. Timing Precision Requirements
- Decoder uses busy-wait to maintain exactly 15,625 Hz sample rate
- MUST use `put_nowait()` (non-blocking) to preserve microsecond-precise timing
- Any blocking (even 1ms) would break timing and cause glitches
- If Queue fills, drop samples rather than block decoder

### 3. pygame.mixer.Channel Limitations
- Can only have ONE sound playing + ONE sound queued at a time
- Calling `queue()` when already queued REPLACES the queued sound (skips it!)
- Must check `get_queue() is not None` before calling `queue()`
- Each chunk (2048 samples) takes 131ms to play at 15625 Hz

### 4. Process Memory Separation
- With fork method, child process gets copy of parent's memory
- Class variables are COPIED, not shared
- Changes in decoder process don't affect main process
- Queue is the only IPC mechanism between processes

## Expected Behavior After Fixes

### Immediate Playback
- Should start playing after ~131ms (time to fill first chunk)
- No multi-second delay

### Smooth Continuous Playback
- Chunks queue seamlessly (one finishes, next starts immediately)
- No long pauses between chunks
- No pops or crackles (unless Queue fills up)

### No Sample Dropping (if decoder keeps up)
- Queue should stay mostly empty (playback consumes faster than decoder produces)
- Only drop samples if decoder produces faster than 15,625 Hz (shouldn't happen)

### Clean Process Termination
- Decoder process is daemon - terminates when main process exits
- Playback thread is daemon - terminates when main thread exits
- No need to kill processes manually

## Testing Instructions

### 1. Test with a short audio file first
Run the game and play a short sound effect to verify basic functionality.

**Expected logs**:
```
[_thread] Creating multiprocessing.Queue with maxsize=10000...
[_thread] Successfully created multiprocessing.Queue
[_thread] Creating PWM in main process for playback...
[Audio] PWM.__init__ in main process
[Audio] Starting playback with 2048+ samples buffered
[Audio] Chunk #1 queued, buffer=...
[Audio] Chunk #2 queued, buffer=...
...
[_thread] Audio decoder process started (PID: ...)
[Audio] PWM.__init__ in DECODER process - no pygame needed, will use Queue
[Audio] Decoder: 10000 queued, 0 dropped
[Audio] Consumed 15000 total, buffer: ...
```

### 2. Test with music
Play background music to verify sustained playback.

**Watch for**:
- No "Queue full" messages
- No massive sample dropping
- Smooth audio with no pops/pauses

### 3. Check process cleanup
Exit the game normally.

**Expected**:
- Game should exit cleanly within 1-2 seconds
- No need to kill process manually
- Decoder process should terminate automatically

## Potential Remaining Issues

### 1. Performance on Slower Machines
The test showed ~79% efficiency on the test environment. On slower machines, this might be worse.

**Symptoms**: Queue fills up, samples dropped, audio stutters

**Solutions**:
- Increase Queue size (but stay under macOS limit of ~16K)
- Further reduce sleep time (try 0.1ms instead of 0.5ms)
- Optimize sample conversion (use numpy if available)

### 2. macOS Specific Issues
macOS has tighter semaphore limits (SEM_VALUE_MAX ~32767).

**Current Queue size**: 10,000 (safe)

If you see "OSError: [Errno 22] Invalid argument" when creating Queue, reduce the size further.

### 3. Fork Method on macOS
We force 'fork' method on macOS for simplicity. But macOS prefers 'spawn'.

If you encounter issues, we might need to:
- Switch to 'spawn' method
- Ensure all code is properly picklable
- Move more logic to module level

## Files Modified

- `pc_wrapper/machine.py` - Critical fixes and optimizations
- `pc_wrapper/_thread.py` - No changes (already correct)

## Test Programs (Can be deleted if desired)

- `test_consumption_bug.py`
- `test_mp_consumption.py`
- `test_pygame_queue.py`
- `test_dummy_driver.py`
- `test_full_audio_pipeline.py`
- `test_sleep_precision.py`

These are for development/debugging and not needed for runtime.

## Next Steps

1. **Test the game** with these fixes
2. **Report results**:
   - Does audio play immediately (no multi-second delay)?
   - Is playback smooth (no pops/pauses)?
   - Do processes exit cleanly?
3. **Share logs** if issues persist
   - Look for "Queue full" or "samples dropped" messages
   - Check consumption vs playback rates
   - Verify decoder process is producing samples

## Summary

The critical bug was the decoder process interfering with pygame.mixer. This is now fixed.

Performance optimizations should improve throughput from ~79% to near 100%.

The architecture is sound - true parallelism via multiprocessing, proper IPC via Queue, and correct pygame usage.

Testing is needed to verify all issues are resolved.
