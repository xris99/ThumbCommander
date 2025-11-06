# Audio Architecture Analysis & Redesign

## Current Issues

### Symptoms
1. Decoder produces samples at full speed (~93K samples in 10 seconds)
2. Playback thread consumes only ~13K samples in same time
3. Queue fills up immediately (10K in 0.64 seconds)
4. 73K+ samples dropped
5. Audio plays only 2 chunks before stopping
6. Consumption only happens AFTER user stops audio

### Root Cause Analysis

**The playback thread is starved by Python's GIL!**

Current architecture:
- **Decoder process**: Separate Python interpreter (no GIL sharing) ✓ WORKS
- **Playback thread**: Runs in MAIN process, SHARES GIL with game loop ✗ PROBLEM

The game loop is:
- Updating display at 60 FPS
- Processing input
- Running timer callbacks
- Constantly holding the GIL

The playback thread only gets CPU time when game loop yields (releases GIL), which is NOT often enough.

### Why Previous Fixes Failed

1. **Removing reinit**: Correct fix but didn't solve GIL issue
2. **Decoupling consumption**: Good idea but thread still starved
3. **Reducing sleep time**: Doesn't matter if thread doesn't run
4. **Batch sizes**: Irrelevant when thread barely runs

## Research: Best Practices

### Option 1: Dedicated Audio Process (RECOMMENDED)
Run audio playback in a separate process (like decoder):
- **Pros**: No GIL sharing, guaranteed CPU time
- **Cons**: Can't use pygame directly from child process

### Option 2: Increase Thread Priority
Use threading priority or nice values:
- **Pros**: Simple change
- **Cons**: May not work, limited by GIL

### Option 3: Replace pygame with pyaudio/sounddevice
Use callback-based audio library:
- **Pros**: Designed for real-time audio
- **Cons**: Large change, new dependency

### Option 4: Write Directly to Audio Device
Use ossaudiodev, alsaaudio, or PyAudio:
- **Pros**: Lower latency, better control
- **Cons**: Platform-specific

### Option 5: Use Shared Memory Instead of Queue
mmap or multiprocessing.shared_memory:
- **Pros**: Faster than Queue
- **Cons**: More complex

## Recommended Architecture

### New Design: Separate Playback Process

```
Main Process (Game Loop)
├─ Display updates
├─ Input handling
├─ Game logic
└─ Monitors playback status

Decoder Process (CPU Core 1)
├─ Reads IMA ADPCM file
├─ Decodes to PCM
└─ Writes to Shared Memory Ring Buffer

Playback Process (CPU Core 2)  ← NEW!
├─ Reads from Shared Memory
├─ Feeds to pygame/pyaudio
└─ Reports status back
```

### Why This Works

1. **No GIL contention**: Each process has own interpreter
2. **Guaranteed CPU time**: OS schedules processes fairly
3. **True parallelism**: Replicates RP2350's dual-core
4. **Shared memory**: Faster than Queue for audio data

### Implementation Plan

1. **Phase 1**: Replace Queue with shared memory ring buffer
2. **Phase 2**: Move playback to separate process
3. **Phase 3**: Test and optimize
4. **Phase 4**: Consider replacing pygame if still issues

## Alternative: Simple Fix

If full rewrite is too much, try:
1. **Move game loop to thread, audio to main**: Reverse the threading
2. **Increase audio thread priority**: `os.nice()` or threading
3. **Reduce game loop frequency**: Run at 30 FPS instead of 60

## Testing Required

Before implementing, test:
1. Does pygame.mixer work at all? (test_simple_channel.py)
2. Is GIL the issue? (profile with py-spy or cProfile)
3. Can we write to audio device directly? (test pyaudio)
