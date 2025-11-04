"""
MicroPython machine module for PC with audio support
Provides PWM and Timer that work with pygame for audio output
Uses multiprocessing for true parallel audio decoding (bypasses GIL)
"""

import threading
import time
import os
import queue
import pc_wrapper._thread as _thread_module

# Lazy pygame import
pygame = None
_audio_initialized = False


def _ensure_pygame():
    """Ensure pygame is imported and mixer is initialized"""
    global pygame, _audio_initialized
    if pygame is None:
        try:
            import pygame as pg
            pygame = pg
        except ImportError:
            return False

    # Check if mixer needs initialization
    if not _audio_initialized and pygame:
        try:
            # Check if mixer is already initialized (by engine_draw.py)
            existing_init = pygame.mixer.get_init()
            if existing_init is not None:
                print(f"[Audio] Mixer already initialized: {existing_init}", flush=True)
                _audio_initialized = True
            else:
                # Mixer not initialized, try to initialize with dummy mode
                import os
                print(f"[Audio] Mixer not initialized, trying dummy mode", flush=True)
                os.environ['SDL_AUDIODRIVER'] = 'dummy'
                pygame.mixer.quit()  # Clean up any failed state
                pygame.mixer.pre_init(frequency=16000, size=-16, channels=1, buffer=512)
                pygame.mixer.init()
                mixer_check = pygame.mixer.get_init()
                print(f"[Audio] Mixer initialized with dummy: {mixer_check}", flush=True)
                _audio_initialized = True
        except Exception as e:
            # Mixer initialization failed completely
            print(f"[Audio] Mixer initialization failed: {e}", flush=True)
            _audio_initialized = True  # Don't keep trying
            return False

    return pygame is not None and pygame.mixer.get_init() is not None


def freq(frequency=None):
    """Get or set CPU frequency - no-op on PC"""
    if frequency is None:
        return 200_000_000  # Return a dummy frequency
    pass


def idle():
    """Idle the CPU - no-op on PC"""
    pass


class Pin:
    """GPIO pin stub"""
    IN = 0
    OUT = 1
    PULL_UP = 2
    PULL_DOWN = 3

    def __init__(self, pin, mode=None, pull=None):
        self.pin = pin
        self.mode = mode
        self.pull = pull
        self._value = 0

    def value(self, val=None):
        if val is None:
            return self._value
        self._value = val

    def on(self):
        self._value = 1

    def off(self):
        self._value = 0


class PWM:
    """
    PWM class that outputs audio through pygame.mixer
    Reinitializes mixer to match source sample rate (no resampling!)
    """

    # Class-level audio state
    _sample_buffer = []
    _active_pwm = None
    _lock = threading.Lock()
    _playback_thread = None
    _stop_playback = False
    _channel = None
    _current_mixer_rate = 16000  # Current pygame.mixer rate
    _current_sound = None  # Keep reference to prevent garbage collection

    # Debug tracking
    _samples_in = 0
    _last_debug_time = 0

    def __init__(self, pin, freq=120000, duty=0):
        """
        Initialize PWM

        Args:
            pin: Pin object (ignored for audio)
            freq: PWM frequency (120kHz carrier, not audio sample rate)
            duty: Initial duty cycle
        """
        self.pin = pin
        self._freq = freq
        self._duty = 0

        # Only set as active PWM if pygame is available
        pygame_available = _ensure_pygame()
        print(f"[Audio] PWM.__init__: pygame available = {pygame_available}, pygame.mixer.get_init() = {pygame.mixer.get_init() if pygame else None}", flush=True)

        if pygame_available:
            # CRITICAL: Properly cleanup old PWM before creating new one
            if PWM._active_pwm is not None:
                print(f"[Audio] Cleaning up old PWM instance before creating new one", flush=True)
                # Stop the old playback thread
                PWM._stop_playback = True

                # Wait for old thread to actually exit (up to 500ms)
                old_thread = PWM._playback_thread
                if old_thread and old_thread.is_alive():
                    for i in range(50):  # 50 * 10ms = 500ms max wait
                        if not old_thread.is_alive():
                            break
                        time.sleep(0.01)
                    print(f"[Audio] Old thread exited: {not old_thread.is_alive()}", flush=True)

                # Stop the mixer channel
                with PWM._lock:
                    if PWM._channel:
                        PWM._channel.stop()
                        print(f"[Audio] Stopped old mixer channel", flush=True)

            # Detect source sample rate from audio.py and reinitialize mixer
            import sys
            source_rate = None
            if 'audio' in sys.modules:
                audio_mod = sys.modules['audio']
                if hasattr(audio_mod, 'audio') and hasattr(audio_mod.audio, 'sample_rate'):
                    source_rate = audio_mod.audio.sample_rate
                    print(f"[Audio] Detected source sample rate: {source_rate} Hz", flush=True)

            # Reinitialize pygame.mixer with source sample rate (no resampling needed!)
            if source_rate and source_rate != PWM._current_mixer_rate:
                print(f"[Audio] Reinitializing mixer from {PWM._current_mixer_rate} Hz to {source_rate} Hz", flush=True)
                pygame.mixer.quit()
                time.sleep(0.05)  # Brief pause for cleanup
                pygame.mixer.pre_init(frequency=source_rate, size=-16, channels=1, buffer=512)
                pygame.mixer.init()
                PWM._current_mixer_rate = source_rate
                print(f"[Audio] Mixer reinitialized: {pygame.mixer.get_init()}", flush=True)

            with PWM._lock:
                PWM._active_pwm = self
                PWM._sample_buffer = []
                PWM._stop_playback = False

                # No resampling needed - direct sample passthrough
                PWM._samples_in = 0
                PWM._last_debug_time = time.time()

                import sys
                print(f"[Audio] PWM initialized for direct passthrough (no resampling)", flush=True)
                sys.stdout.flush()

                # Create dedicated mixer channel for audio playback
                PWM._channel = pygame.mixer.Channel(0)
                print(f"[Audio] Created fresh mixer channel", flush=True)

                # Always start a new playback thread (old one has been stopped)
                PWM._playback_thread = threading.Thread(target=self._audio_player_thread, daemon=True)
                PWM._playback_thread.start()
                print(f"[Audio] Started new playback thread", flush=True)

    def freq(self, val=None):
        """Get or set PWM frequency"""
        if val is None:
            return self._freq
        self._freq = val

    def duty(self, val=None):
        """Get or set duty cycle (0-1023)"""
        if val is None:
            return self._duty
        self._duty = val

    def duty_u16(self, val=None):
        """
        Get or set 16-bit duty cycle (0-65535)
        This is the main method used by audio.py to output samples
        Direct passthrough - no resampling (mixer matches source rate)
        """
        if val is None:
            return self._duty

        self._duty = val

        # Send sample to audio buffer ONLY if we're the active PWM
        # This prevents old audio threads from polluting the buffer
        if PWM._active_pwm is not self:
            return  # Silently discard samples from inactive PWM instances

        # Check if we're in the audio decoder process (multiprocessing)
        audio_queue = _thread_module.get_audio_queue()

        if audio_queue is not None and _thread_module.is_audio_process():
            # IN DECODER PROCESS: Send to multiprocessing Queue (IPC to main process)
            try:
                audio_queue.put_nowait(val)  # Non-blocking put
                PWM._samples_in += 1
            except:
                pass  # Queue full, drop sample (shouldn't happen with 50K capacity)

            # Debug output every 5000 samples
            if PWM._samples_in % 5000 == 0:
                print(f"[Audio] Decoder process: {PWM._samples_in} samples sent", flush=True)
        else:
            # IN MAIN PROCESS: Use local buffer (fallback, shouldn't normally happen)
            with PWM._lock:
                PWM._sample_buffer.append(val)
                PWM._samples_in += 1

    @staticmethod
    def _audio_player_thread():
        """
        Background thread for audio playback using pygame.mixer.Sound
        Consumes samples from multiprocessing.Queue (sent by decoder process)
        """
        chunk_size = 2048  # Chunk size in samples
        headroom = 8192    # Initial buffer before starting
        chunks_played = 0
        playback_started = False

        # Import struct for bytes conversion
        import struct

        # Get the multiprocessing queue
        audio_queue = _thread_module.get_audio_queue()

        print(f"[Audio] Playback thread starting, consuming from multiprocessing.Queue", flush=True)
        print(f"[Audio] Waiting for {headroom} samples before playback", flush=True)

        while not PWM._stop_playback:
            # Consume samples from multiprocessing Queue into local buffer
            try:
                while len(PWM._sample_buffer) < headroom + chunk_size:
                    # Get sample from decoder process (with timeout to allow checking stop flag)
                    sample = audio_queue.get(timeout=0.01)
                    with PWM._lock:
                        PWM._sample_buffer.append(sample)
            except queue.Empty:
                pass  # No samples available, continue

            # Check buffer size
            with PWM._lock:
                buffer_size = len(PWM._sample_buffer)
                active_pwm = PWM._active_pwm

            # If no active PWM, exit thread
            if active_pwm is None:
                print(f"[Audio] No active PWM, exiting playback thread", flush=True)
                break

            # Wait for initial buffer fill
            if not playback_started:
                if buffer_size >= headroom:
                    playback_started = True
                    print(f"[Audio] Buffer filled to {buffer_size} samples, starting playback", flush=True)
                else:
                    time.sleep(0.01)
                    continue

            # Extract chunk
            chunk = None
            with PWM._lock:
                buffer_size = len(PWM._sample_buffer)
                if buffer_size > 0:
                    actual_chunk_size = min(buffer_size, chunk_size)
                    chunk = PWM._sample_buffer[:actual_chunk_size]
                    PWM._sample_buffer = PWM._sample_buffer[actual_chunk_size:]

            if chunk:
                chunks_played += 1
                if chunks_played <= 5 or chunks_played % 50 == 0:
                    print(f"[Audio] Playing chunk #{chunks_played}: {len(chunk)} samples, buffer: {buffer_size}", flush=True)

                try:
                    # Check if mixer is still initialized
                    if not pygame.mixer.get_init():
                        print(f"[Audio] Mixer shut down, exiting playback thread", flush=True)
                        break

                    # Convert to bytes without numpy (avoids segfaults)
                    # Convert samples to signed 16-bit integers
                    signed_samples = [max(-32768, min(32767, int(s) - 32768)) for s in chunk]

                    # Pack all samples at once using format string (much faster)
                    audio_bytes = struct.pack('<' + 'h' * len(signed_samples), *signed_samples)

                    # Create Sound and keep reference (prevents garbage collection)
                    PWM._current_sound = pygame.mixer.Sound(buffer=audio_bytes)

                    # Play sound immediately on dedicated channel
                    PWM._channel.play(PWM._current_sound)

                    # Wait for channel to finish playback
                    while PWM._channel.get_busy() and not PWM._stop_playback:
                        time.sleep(0.010)  # Check every 10ms

                    if chunks_played <= 10:
                        with PWM._lock:
                            current_buffer = len(PWM._sample_buffer)
                        print(f"[Audio] Played chunk #{chunks_played}, buffer={current_buffer}", flush=True)

                except Exception as e:
                    print(f"[Audio] Error playing chunk #{chunks_played}: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    # If mixer error, exit thread
                    if "mixer" in str(e).lower():
                        break
            else:
                # Buffer empty, wait for decoder
                time.sleep(0.01)

    def _cleanup(self):
        """Stop audio playback"""
        print(f"[Audio] PWM._cleanup() called", flush=True)
        with PWM._lock:
            PWM._sample_buffer = []
            if PWM._channel:
                PWM._channel.stop()
                print(f"[Audio] Stopped pygame mixer channel", flush=True)

    def deinit(self):
        """Deinitialize PWM"""
        print(f"[Audio] PWM.deinit() called, is_active={PWM._active_pwm is self}", flush=True)
        if PWM._active_pwm is self:
            self._cleanup()
            with PWM._lock:
                PWM._active_pwm = None
            print(f"[Audio] PWM deinitialized, active_pwm set to None", flush=True)


class Timer:
    """Timer class for callbacks"""
    PERIODIC = 1
    ONE_SHOT = 0

    def __init__(self, timer_id=-1):
        self.timer_id = timer_id
        self._thread = None
        self._stop_event = None
        self._callback = None
        self._period_ms = 0
        self._mode = None

    def init(self, mode=None, period=None, freq=None, callback=None):
        """Initialize timer"""
        self.deinit()
        self._callback = callback
        self._mode = mode

        if period is not None:
            self._period_ms = period
        elif freq is not None:
            self._period_ms = 1000.0 / freq
        else:
            self._period_ms = 100

        if callback is not None:
            self._stop_event = threading.Event()
            if mode == Timer.PERIODIC:
                self._thread = threading.Thread(target=self._periodic_worker, daemon=True)
            else:
                self._thread = threading.Thread(target=self._oneshot_worker, daemon=True)
            self._thread.start()

    def _periodic_worker(self):
        """Worker thread for periodic callbacks"""
        callback_count = 0
        while not self._stop_event.is_set():
            try:
                if self._callback:
                    self._callback(self)
                    callback_count += 1
                    # Log first 5 callbacks and every 30th after
                    if callback_count <= 5 or callback_count % 30 == 0:
                        print(f"[Timer] Callback #{callback_count} completed", flush=True)
            except Exception as e:
                print(f"[Timer] ERROR in callback: {e}", flush=True)
                import traceback
                traceback.print_exc()
            timeout = self._period_ms / 1000.0
            self._stop_event.wait(timeout)

    def _oneshot_worker(self):
        """Worker thread for one-shot callbacks"""
        timeout = self._period_ms / 1000.0
        self._stop_event.wait(timeout)
        if not self._stop_event.is_set():
            try:
                if self._callback:
                    self._callback(self)
            except:
                pass

    def deinit(self):
        """Stop and deinitialize timer"""
        if self._stop_event:
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._stop_event = None
        self._callback = None


class SPI:
    """SPI stub"""
    def __init__(self, bus, baudrate=1000000, polarity=0, phase=0):
        self.bus = bus
        self.baudrate = baudrate

    def write(self, buf):
        pass

    def read(self, nbytes):
        return bytearray(nbytes)

    def readinto(self, buf):
        pass

    def write_readinto(self, write_buf, read_buf):
        pass

    def deinit(self):
        pass


# Memory access stub
mem32 = None
