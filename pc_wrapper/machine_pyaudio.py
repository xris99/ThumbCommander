"""
NEW AUDIO ARCHITECTURE: PyAudio with callback-based playback

Why this fixes the issues:
1. PyAudio callbacks run in C thread (bypasses Python GIL!)
2. Callbacks are triggered by audio hardware, not Python threading
3. Simple consumer: just read from Queue and feed to stream
4. No pygame.mixer complexity

This replicates the hardware behavior where audio runs independently.
"""

import queue
import struct
import threading

# Try to import pyaudio
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("[Audio] PyAudio not available, falling back to pygame")

class PyAudioPWM:
    """PWM audio output using PyAudio (callback-based, bypasses GIL)"""

    # Class variables
    _audio_stream = None
    _audio_queue = None
    _sample_buffer = []
    _lock = threading.Lock()
    _active = False
    _pyaudio = None

    def __init__(self, pin, freq=120000):
        """Initialize PyAudio stream"""
        if not PYAUDIO_AVAILABLE:
            print("[Audio] PyAudio not available!")
            return

        # Get queue from _thread module
        import pc_wrapper._thread as _thread_module
        PyAudioPWM._audio_queue = _thread_module.get_audio_queue()

        if PyAudioPWM._audio_queue is None:
            print("[Audio] No audio queue available")
            return

        # Check if this is decoder process
        if _thread_module.is_audio_process():
            print("[Audio] PyAudio PWM in decoder process - will send to Queue")
            PyAudioPWM._active = True
            return

        # Main process: initialize PyAudio
        print("[Audio] Initializing PyAudio for playback...")

        if PyAudioPWM._pyaudio is None:
            PyAudioPWM._pyaudio = pyaudio.PyAudio()

        # Open stream with callback
        PyAudioPWM._active = True
        PyAudioPWM._sample_buffer = []

        try:
            PyAudioPWM._audio_stream = PyAudioPWM._pyaudio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=15625,
                output=True,
                frames_per_buffer=1024,  # 65ms chunks
                stream_callback=self._audio_callback
            )
            PyAudioPWM._audio_stream.start_stream()
            print(f"[Audio] PyAudio stream started at 15625 Hz")
        except Exception as e:
            print(f"[Audio] Failed to open PyAudio stream: {e}")
            PyAudioPWM._active = False

    @staticmethod
    def _audio_callback(in_data, frame_count, time_info, status):
        """
        Audio callback - called by PortAudio from C thread (bypasses GIL!)

        This is THE KEY to fixing the GIL starvation issue.
        PortAudio calls this from a high-priority audio thread.
        """
        # Consume from Queue
        consumed = 0
        with PyAudioPWM._lock:
            while len(PyAudioPWM._sample_buffer) < frame_count * 2:  # Keep buffer full
                try:
                    # Try to get samples from queue
                    for _ in range(min(1024, frame_count * 2)):
                        sample = PyAudioPWM._audio_queue.get_nowait()
                        PyAudioPWM._sample_buffer.append(sample)
                        consumed += 1
                except queue.Empty:
                    break

            # Extract samples for playback
            if len(PyAudioPWM._sample_buffer) >= frame_count:
                samples = PyAudioPWM._sample_buffer[:frame_count]
                PyAudioPWM._sample_buffer = PyAudioPWM._sample_buffer[frame_count:]
            else:
                # Not enough samples - pad with silence
                samples = PyAudioPWM._sample_buffer + [32768] * (frame_count - len(PyAudioPWM._sample_buffer))
                PyAudioPWM._sample_buffer = []

        # Convert to signed 16-bit PCM
        signed_samples = [max(-32768, min(32767, int(s) - 32768)) for s in samples]
        audio_bytes = struct.pack('<' + 'h' * len(signed_samples), *signed_samples)

        if consumed > 0 and consumed % 5000 == 0:
            print(f"[Audio] Callback consumed {consumed} samples, buffer={len(PyAudioPWM._sample_buffer)}", flush=True)

        return (audio_bytes, pyaudio.paContinue)

    def duty_u16(self, val=None):
        """Send sample to queue (decoder) or buffer (main)"""
        if val is None:
            return 0

        if not PyAudioPWM._active:
            return

        # Check if we're in decoder process
        import pc_wrapper._thread as _thread_module
        if _thread_module.is_audio_process() and PyAudioPWM._audio_queue:
            # Decoder: send to queue
            try:
                PyAudioPWM._audio_queue.put_nowait(val)
            except queue.Full:
                pass  # Drop sample to maintain timing
        else:
            # Main process: add to buffer (callback will consume)
            with PyAudioPWM._lock:
                PyAudioPWM._sample_buffer.append(val)

    def deinit(self):
        """Clean up PyAudio"""
        if PyAudioPWM._audio_stream:
            try:
                PyAudioPWM._audio_stream.stop_stream()
                PyAudioPWM._audio_stream.close()
                PyAudioPWM._audio_stream = None
            except:
                pass

        PyAudioPWM._active = False

    @staticmethod
    def cleanup_all():
        """Clean up all PyAudio resources"""
        if PyAudioPWM._audio_stream:
            try:
                PyAudioPWM._audio_stream.stop_stream()
                PyAudioPWM._audio_stream.close()
            except:
                pass

        if PyAudioPWM._pyaudio:
            try:
                PyAudioPWM._pyaudio.terminate()
            except:
                pass

        PyAudioPWM._pyaudio = None
        PyAudioPWM._audio_stream = None
        PyAudioPWM._active = False


# Test if we should use PyAudio or fall back to pygame
USE_PYAUDIO = PYAUDIO_AVAILABLE

if USE_PYAUDIO:
    print("[Audio] Using PyAudio backend (callback-based, bypasses GIL)")
else:
    print("[Audio] Using pygame backend (thread-based, affected by GIL)")
