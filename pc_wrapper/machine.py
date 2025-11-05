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

                # CRITICAL: Only start playback thread in MAIN process, not in decoder process
                if _thread_module.is_audio_process():
                    print(f"[Audio] Running in decoder process - NO playback thread (will send samples via Queue)", flush=True)
                else:
                    # In main process - start playback thread
                    print(f"[Audio] Running in main process - starting playback thread", flush=True)

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
            # CRITICAL: Must use put_nowait() to preserve decoder's microsecond-precise timing!
            # The audio_loop uses busy-wait to maintain exact 15625 Hz sample rate.
            # Any blocking (even 1ms) breaks this precision and causes audio glitches.
            # If Queue fills, playback can't keep up - drop samples to maintain timing.
            try:
                audio_queue.put_nowait(val)  # Non-blocking - critical for timing precision!
                PWM._samples_in += 1
            except queue.Full:
                # Queue full (32K samples = ~2 sec) - playback severely lagging
                # Drop sample to maintain decoder timing (critical for busy-wait loop)
                if not hasattr(PWM, '_samples_dropped'):
                    PWM._samples_dropped = 0
                PWM._samples_dropped += 1
                if PWM._samples_dropped % 5000 == 0:
                    print(f"[Audio] WARNING: Dropped {PWM._samples_dropped} samples (Queue full)", flush=True)

            # Debug output every 10000 samples
            if PWM._samples_in % 10000 == 0:
                dropped = getattr(PWM, '_samples_dropped', 0)
                print(f"[Audio] Decoder: {PWM._samples_in} queued, {dropped} dropped", flush=True)
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

        ARCHITECTURE:
        1. Consume ALL available samples from Queue into buffer (fast!)
        2. Feed chunks from buffer to pygame when ready (controlled rate)
        3. pygame.mixer.Channel can only queue ONE sound at a time
        """
        chunk_size = 2048  # Chunk size in samples (131ms at 15625 Hz)
        chunks_played = 0
        playback_started = False

        # Import struct for bytes conversion
        import struct

        # Get the multiprocessing queue
        audio_queue = _thread_module.get_audio_queue()

        if audio_queue is None:
            print(f"[Audio] ERROR: audio_queue is None! Cannot consume samples", flush=True)
            return

        print(f"[Audio] Playback thread starting", flush=True)

        consume_count = 0
        last_consume_log = 0

        # Main loop: SEPARATE consumption from playback!
        while not PWM._stop_playback:
            # === PHASE 1: CONSUME ALL AVAILABLE SAMPLES ===
            # This runs as fast as possible to empty the Queue
            consumed_this_round = 0
            while True:  # Keep consuming until Queue is empty
                batch = []
                try:
                    # Get up to 1024 samples in one batch
                    for _ in range(1024):
                        batch.append(audio_queue.get_nowait())
                except queue.Empty:
                    pass  # No more samples available

                if batch:
                    with PWM._lock:
                        PWM._sample_buffer.extend(batch)
                    consumed_this_round += len(batch)
                else:
                    break  # Queue is empty, move to playback phase

            if consumed_this_round > 0:
                consume_count += consumed_this_round
                if consume_count - last_consume_log >= 5000:
                    with PWM._lock:
                        buf_size = len(PWM._sample_buffer)
                    print(f"[Audio] Consumed {consume_count} total, buffer: {buf_size}", flush=True)
                    last_consume_log = consume_count

            # === PHASE 2: PLAYBACK ===
            # Check buffer size and active PWM
            with PWM._lock:
                buffer_size = len(PWM._sample_buffer)
                active_pwm = PWM._active_pwm

            if active_pwm is None:
                print(f"[Audio] No active PWM, exiting playback thread", flush=True)
                break

            # Start playback as soon as we have one chunk
            if not playback_started:
                if buffer_size >= chunk_size:
                    playback_started = True
                    print(f"[Audio] Starting playback with {buffer_size} samples buffered", flush=True)
                else:
                    time.sleep(0.001)  # Wait briefly for more samples
                    continue

            # Check if pygame is ready for next chunk
            # pygame.mixer.Channel can only have ONE queued sound!
            if PWM._channel.get_queue() is not None:
                # Already have a queued sound, wait for it to start playing
                time.sleep(0.001)  # Brief wait
                continue

            # Extract chunk if available
            if buffer_size >= chunk_size:
                with PWM._lock:
                    chunk = PWM._sample_buffer[:chunk_size]
                    PWM._sample_buffer = PWM._sample_buffer[chunk_size:]

                chunks_played += 1

                try:
                    # Check if mixer is still initialized
                    if not pygame.mixer.get_init():
                        print(f"[Audio] Mixer shut down, exiting", flush=True)
                        break

                    # Convert to signed 16-bit PCM
                    signed_samples = [max(-32768, min(32767, int(s) - 32768)) for s in chunk]
                    audio_bytes = struct.pack('<' + 'h' * len(signed_samples), *signed_samples)

                    # Create Sound
                    sound = pygame.mixer.Sound(buffer=audio_bytes)

                    # Queue to channel (will play after current sound finishes)
                    # First chunk uses play(), rest use queue()
                    if chunks_played == 1:
                        PWM._channel.play(sound)
                    else:
                        PWM._channel.queue(sound)

                    if chunks_played <= 10 or chunks_played % 50 == 0:
                        with PWM._lock:
                            buf = len(PWM._sample_buffer)
                        print(f"[Audio] Chunk #{chunks_played} queued, buffer={buf}", flush=True)

                except Exception as e:
                    print(f"[Audio] Error: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    break
            else:
                # Not enough samples for a chunk yet
                time.sleep(0.001)  # Wait briefly

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
