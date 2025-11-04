"""
MicroPython _thread module compatibility for PC
Uses multiprocessing for audio_loop to achieve true parallelism (bypass GIL)
"""

import threading
import multiprocessing as mp
from multiprocessing import Queue

# Global state for audio decoder process
_audio_sample_queue = None
_audio_process = None
_is_audio_process = False  # Flag to detect if we're IN the audio process


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
        print("[_thread] Detected audio_loop - using multiprocessing.Process for true parallelism")

        # Create IPC queue for samples (50K capacity = ~3 seconds at 15625 Hz)
        _audio_sample_queue = Queue(maxsize=50000)

        # Wrapper to run audio_loop in separate process
        def audio_process_wrapper():
            """Wrapper that runs in the decoder process"""
            global _is_audio_process
            _is_audio_process = True

            # Set process title for debugging
            try:
                import setproctitle
                setproctitle.setproctitle('thumby-audio-decoder')
            except ImportError:
                pass

            print(f"[_thread] Audio decoder process started (PID: {mp.current_process().pid})")

            # Run the audio loop
            try:
                function(*args)
            except Exception as e:
                print(f"[_thread] Audio process error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                print("[_thread] Audio decoder process exiting")

        # Start as separate process (bypasses GIL!)
        _audio_process = mp.Process(target=audio_process_wrapper, daemon=True)
        _audio_process.start()

        print(f"[_thread] Audio process started with PID: {_audio_process.pid}")

        # Return process ID (mimics thread ID)
        return _audio_process.pid
    else:
        # Use normal threading for other threads (Timer callbacks, etc.)
        print(f"[_thread] Starting thread for {function.__name__} using threading.Thread")
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


# Expose the sample queue for PWM to use
def get_audio_queue():
    """Get the audio sample queue (for PWM.duty_u16 to use)"""
    return _audio_sample_queue


def is_audio_process():
    """Check if we're running in the audio decoder process"""
    return _is_audio_process
