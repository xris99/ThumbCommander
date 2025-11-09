"""
MicroPython _thread module compatibility for PC
Uses multiprocessing for audio_loop to achieve true parallelism (bypass GIL)
"""

import threading
import multiprocessing as mp
from multiprocessing import Queue

# Note: Multiprocessing start method must be set in run_pc.py BEFORE any imports
# that might use multiprocessing (like pygame). This ensures 'fork' method is used.

# Global state for audio decoder process
_audio_sample_queue = None
_audio_process = None
_is_audio_process = False  # Flag to detect if we're IN the audio process

# Store function/args for audio process (needed for 'spawn' method pickling)
_audio_function = None
_audio_args = None


# Export standard _thread module attributes (required by other Python modules)
allocate_lock = threading.Lock
LockType = threading.Lock
error = RuntimeError  # _thread.error is RuntimeError


def _audio_process_wrapper():
    """
    Wrapper that runs in the decoder process
    Must be module-level function for 'spawn' method pickling
    """
    global _is_audio_process, _audio_function, _audio_args
    _is_audio_process = True

    # Set process title for debugging
    try:
        import setproctitle
        setproctitle.setproctitle('thumby-audio-decoder')
    except ImportError:
        pass

    print(f"[_thread] Audio decoder process started (PID: {mp.current_process().pid})", flush=True)

    # Run the audio loop
    try:
        _audio_function(*_audio_args)
    except Exception as e:
        print(f"[_thread] Audio process error: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        print("[_thread] Audio decoder process exiting", flush=True)


def start_new_thread(function, args):
    """
    Start a new thread or process

    For audio_loop: Uses multiprocessing.Process for true parallelism
    For others: Uses threading.Thread

    This replicates RP2350's dual-core architecture:
    - Core 0 (main process): Game loop, Timer callbacks, playback
    - Core 1 (audio process): audio_loop with busy-wait timing
    """
    global _audio_sample_queue, _audio_process

    # Detect if this is the audio decoder thread
    if function.__name__ == 'audio_loop':
        global _audio_function, _audio_args

        print(f"[_thread] Detected audio_loop - using multiprocessing.Process for true parallelism", flush=True)
        print(f"[_thread] Current _audio_process: {_audio_process}", flush=True)
        print(f"[_thread] Current mp method: {mp.get_start_method()}", flush=True)

        # Check if we already have a running process - TERMINATE it for new audio!
        if _audio_process is not None:
            print(f"[_thread] Found existing _audio_process, checking if alive...", flush=True)
            is_alive = _audio_process.is_alive()
            print(f"[_thread] Process is_alive: {is_alive}", flush=True)
            if is_alive:
                print("[_thread] Terminating old audio process for new audio file", flush=True)
                _audio_process.terminate()
                _audio_process.join(timeout=0.5)  # Wait up to 500ms
                if _audio_process.is_alive():
                    print("[_thread] WARNING: Old process didn't terminate, killing it", flush=True)
                    _audio_process.kill()
                print("[_thread] Old audio process terminated", flush=True)
            else:
                print("[_thread] Old audio process already dead", flush=True)

        # Create IPC queue for samples
        # Note: macOS has SEM_VALUE_MAX limit (~32767), stay well below it
        # Smaller queue = lower latency (immediate playback like real hardware)
        queue_size = 10000  # ~640ms at 15625 Hz - enough buffering, safe for macOS
        print(f"[_thread] Creating multiprocessing.Queue with maxsize={queue_size}...", flush=True)
        try:
            _audio_sample_queue = Queue(maxsize=queue_size)
            print(f"[_thread] Successfully created multiprocessing.Queue with capacity {queue_size}", flush=True)
        except Exception as e:
            print(f"[_thread] ERROR creating Queue: {e}", flush=True)
            import traceback
            traceback.print_exc()
            print(f"[_thread] Falling back to threading.Thread (no multiprocessing)", flush=True)
            # Fall back to threading
            t = threading.Thread(target=function, args=args, daemon=True)
            t.start()
            return t.ident

        # CRITICAL: Create PWM in main process for playback BEFORE starting decoder
        print("[_thread] Creating PWM in main process for playback...", flush=True)
        try:
            from machine import PWM, Pin
            # Create PWM instance in main process - this will start the playback thread
            main_pwm = PWM(Pin(23), freq=120000)
            print(f"[_thread] PWM created in main process", flush=True)
        except Exception as e:
            print(f"[_thread] ERROR creating main process PWM: {e}", flush=True)
            import traceback
            traceback.print_exc()

        # Store function and args for the process wrapper (needed for 'spawn' pickling)
        _audio_function = function
        _audio_args = args

        # Start as separate process (bypasses GIL!)
        print("[_thread] Creating mp.Process...", flush=True)
        try:
            _audio_process = mp.Process(target=_audio_process_wrapper, daemon=True)
            print(f"[_thread] Process object created: {_audio_process}", flush=True)

            print("[_thread] Starting process...", flush=True)
            _audio_process.start()
            print("[_thread] Process.start() returned", flush=True)

            print(f"[_thread] Audio process started with PID: {_audio_process.pid}", flush=True)

            # Return process ID (mimics thread ID)
            return _audio_process.pid
        except Exception as e:
            print(f"[_thread] ERROR: Failed to start audio process: {e}", flush=True)
            import traceback
            traceback.print_exc()
            # Fall back to threading
            print(f"[_thread] Falling back to threading.Thread", flush=True)
            t = threading.Thread(target=function, args=args, daemon=True)
            t.start()
            return t.ident
    else:
        # Use normal threading for other threads (Timer callbacks, etc.)
        print(f"[_thread] Starting thread for {function.__name__} using threading.Thread", flush=True)
        t = threading.Thread(target=function, args=args, daemon=True)
        t.start()
        return t.ident


def get_ident():
    """Get current thread/process identifier"""
    if _is_audio_process:
        return mp.current_process().pid
    else:
        return threading.get_ident()


def exit():
    """Exit current thread/process"""
    if _is_audio_process:
        # In audio process - exit process
        import sys
        sys.exit(0)
    else:
        # In main process - exit thread
        import sys
        sys.exit()


def stack_size(size=None):
    """Get/set thread stack size (ignored, for compatibility)"""
    if size is None:
        return threading.stack_size()
    return threading.stack_size(size)


# Expose the sample queue for PWM to use
def get_audio_queue():
    """Get the audio sample queue (for PWM.duty_u16 to use)"""
    return _audio_sample_queue


def is_audio_process():
    """Check if we're running in the audio decoder process"""
    return _is_audio_process
