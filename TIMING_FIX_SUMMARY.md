# Critical Timing Precision Fixes for Audio Playback

## Problem Analysis

The audio wrapper for audio.py on PC was experiencing audio quality issues (pops and clicks after first chunk) due to **catastrophically imprecise timing** in the PC wrapper implementations.

### Root Causes Identified

#### 1. **utime.py: Millisecond Precision for Microsecond Requirements** ❌

**Problem:**
```python
def ticks_us():
    return int(_time.time() * 1000000)
```

- `time.time()` has only **~1ms precision** (1000 microseconds)
- Audio at 15625 Hz requires samples every **64 microseconds**
- The busy-wait timing loop in audio.py couldn't work with 1000µs precision
- `ticks_us()` returned the same value ~1000 times, then suddenly jumped

**Impact:** The audio thread's precise timing loop (audio.py:194-200) would either:
- Exit immediately (if already past target time)
- Spin uselessly for milliseconds with stale time values
- Completely destroy sample timing, causing pops and clicks

#### 2. **machine.Timer: Millisecond Jitter in Buffer Fills** ❌

**Problem:**
```python
self._stop_event.wait(timeout)  # Python's Event.wait() has millisecond jitter
```

- Timer fills audio buffers at 30 Hz (33ms period)
- `threading.Event.wait()` can wake up early/late by milliseconds
- Irregular buffer fills caused timing desynchronization

**Impact:** Buffer fills would happen at irregular intervals, leading to:
- Audio buffer underruns
- Sample timing drift
- Eventual audio glitches

#### 3. **PWM Thread: Inadequate Error Handling** ⚠️

**Problem:**
- No verification that pygame.mixer was still initialized before playing chunks
- No verification that channel was valid
- Cryptic error messages without stack traces

**Impact:**
- "Invalid audio device ID" errors
- "mixer not initialized" errors
- Difficult to debug root cause

---

## Solutions Implemented

### 1. **High-Precision Timing in utime.py** ✅

```python
import time as _time

# Use perf_counter for nanosecond-precision timing
_base_time = _time.perf_counter()

def ticks_us():
    """
    Get microsecond counter with high precision
    Uses perf_counter() which has nanosecond resolution
    """
    return int((_time.perf_counter() - _base_time) * 1000000)
```

**Benefits:**
- `time.perf_counter()` has **nanosecond resolution** on most systems
- True microsecond precision for audio timing
- Monotonic clock (not affected by system time adjustments)
- Enables precise 64µs sample timing at 15625 Hz

### 2. **High-Precision Timer with Hybrid Sleep** ✅

```python
def _periodic_worker(self):
    """
    Worker thread for periodic callbacks with high-precision timing
    Uses hybrid sleep: coarse sleep + busy-wait for precision
    """
    next_time = time.perf_counter() + (self._period_ms / 1000.0)

    while not self._stop_event.is_set():
        # Execute callback
        if self._callback:
            self._callback(self)

        # Hybrid sleep for precision
        current_time = time.perf_counter()
        sleep_time = next_time - current_time

        if sleep_time > 0:
            # Sleep for most of the time (low CPU)
            if sleep_time > 0.001:  # More than 1ms
                time.sleep(sleep_time - 0.001)

            # Busy-wait for final precision (high accuracy)
            while time.perf_counter() < next_time:
                if self._stop_event.is_set():
                    return
                time.sleep(0)  # Yield to other threads

        # Schedule next callback (no drift!)
        next_time += (self._period_ms / 1000.0)
```

**Benefits:**
- Coarse sleep reduces CPU usage
- Busy-wait provides sub-millisecond precision
- Cumulative timing (no drift from repeated scheduling)
- Accurate 30 Hz buffer fills

### 3. **Enhanced PWM Error Handling** ✅

```python
# Verify mixer is still initialized before playing
mixer_info = pygame.mixer.get_init()
if mixer_info is None:
    print(f"[Audio] Error: mixer not initialized")
    break

# Verify channel is still valid
if PWM._channel is None:
    print(f"[Audio] Error: channel is None")
    break

# ... play audio with full exception handling ...
except Exception as e:
    print(f"[Audio] Error playing chunk: {e}")
    import traceback
    traceback.print_exc()
```

**Benefits:**
- Graceful handling of mixer issues
- Clear error messages with context
- Full stack traces for debugging
- Prevents cryptic error messages

---

## Expected Results

With these fixes, audio playback should:
1. ✅ Play all chunks correctly (not just the first one)
2. ✅ Eliminate pops and clicks caused by timing issues
3. ✅ Maintain consistent sample timing throughout playback
4. ✅ Handle buffer fills at precise 30 Hz intervals
5. ✅ Provide clear error messages if issues occur

---

## Technical Notes

### Timing Precision Comparison

| Method | Precision | Suitable for Audio? |
|--------|-----------|---------------------|
| `time.time()` | ~1ms (1000µs) | ❌ No |
| `time.perf_counter()` | ~1ns | ✅ Yes |
| **Required for 15625Hz** | **64µs** | |

### CPU Usage Consideration

The hybrid sleep approach (coarse sleep + busy-wait) balances:
- **CPU efficiency:** Coarse sleep for most of the wait time
- **Timing precision:** Busy-wait for final <1ms ensures accuracy

---

## Files Modified

1. **pc_wrapper/utime.py**
   - Replaced `time.time()` with `time.perf_counter()`
   - Added base time reference for consistent timing

2. **pc_wrapper/machine.py**
   - Replaced `Event.wait()` with hybrid sleep in Timer
   - Added safety checks in PWM playback thread
   - Enhanced error handling and logging

---

## Testing Recommendations

1. Run the game with audio playback
2. Monitor console for timing-related debug messages
3. Verify all audio chunks play correctly
4. Check for pops/clicks (should be eliminated)
5. Monitor CPU usage (should be reasonable, not 100%)

---

## _thread Module

The standard Python `_thread` module is used directly without wrapping. This is correct because:
- `_thread.start_new_thread()` is Python's low-level threading API
- The audio.py code uses it correctly
- The issue was **timing within the thread**, not the threading mechanism itself
- Python's native threading is sufficient when timing is precise

---

## Conclusion

The audio issues were caused by **timing precision problems**, not the audio implementation itself. The audio.py code is correct, but it requires microsecond-precision timing that the original PC wrapper didn't provide.

With these fixes, the PC wrapper now provides:
- ✅ **Nanosecond-precision timing** via `perf_counter()`
- ✅ **Sub-millisecond timer accuracy** via hybrid sleep
- ✅ **Robust error handling** for debugging

This should resolve the "only pops after first chunk" issue completely.
