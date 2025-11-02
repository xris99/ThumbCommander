"""
MicroPython machine module for PC with audio support
Provides PWM and Timer that work with pygame for audio output
"""

import threading
import time
import os
import numpy as np

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
    Implements real-time sample rate conversion to match pygame mixer rate
    """

    # Class-level audio state
    _sample_buffer = []
    _active_pwm = None
    _lock = threading.Lock()
    _playback_thread = None
    _stop_playback = False
    _channel = None

    # Resampling state
    _source_sample_rate = None
    _target_sample_rate = 16000  # Pygame mixer rate
    _resample_ratio = 1.0
    _resample_position = 0.0  # Fractional sample position
    _last_input_sample = 32768  # Previous sample for interpolation
    _resampler_initialized = False

    # Debug tracking
    _samples_in = 0
    _samples_out = 0
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

            with PWM._lock:
                PWM._active_pwm = self
                PWM._sample_buffer = []
                PWM._stop_playback = False

                # Reset resampler state - CRITICAL for each new audio file
                PWM._source_sample_rate = None
                PWM._resample_ratio = 1.0
                PWM._resample_position = 0.0
                PWM._last_input_sample = 32768
                PWM._resampler_initialized = False

                # Reset debug tracking
                PWM._samples_in = 0
                PWM._samples_out = 0
                PWM._last_debug_time = time.time()

                # Get mixer rate
                mixer_info = pygame.mixer.get_init()
                if mixer_info:
                    PWM._target_sample_rate = mixer_info[0]

                import sys
                print(f"[Audio] PWM reinitialized, buffer cleared, resampler reset", flush=True)
                sys.stdout.flush()

                # ALWAYS create a fresh mixer channel for each audio file
                # This ensures the channel is in a clean state
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
        Implements real-time sample rate conversion
        """
        if val is None:
            return self._duty

        self._duty = val

        # Send sample to audio buffer ONLY if we're the active PWM
        # This prevents old audio threads from polluting the buffer
        if PWM._active_pwm is not self:
            return  # Silently discard samples from inactive PWM instances

        # Process sample (resampling and buffering)
        if True:
            # Detect source sample rate on first samples
            if not PWM._resampler_initialized:
                import sys
                try:
                    if 'audio' in sys.modules:
                        audio_mod = sys.modules['audio']
                        if hasattr(audio_mod, 'audio') and hasattr(audio_mod.audio, 'sample_rate'):
                            PWM._source_sample_rate = audio_mod.audio.sample_rate
                            PWM._resample_ratio = PWM._target_sample_rate / PWM._source_sample_rate
                            PWM._resampler_initialized = True
                            print(f"[Audio] Resampler config: {PWM._source_sample_rate} Hz → {PWM._target_sample_rate} Hz (ratio: {PWM._resample_ratio:.4f})")
                except Exception as e:
                    print(f"[Audio] Error detecting sample rate: {e}")
                    pass

                # If we still don't have rate info, assume 1:1 (no resampling)
                if not PWM._resampler_initialized:
                    PWM._resample_ratio = 1.0
                    PWM._resampler_initialized = True
                    print(f"[Audio] No sample rate detected, using 1:1 passthrough")

            # Track input samples
            PWM._samples_in += 1

            # Apply resampling if needed
            if PWM._resample_ratio == 1.0:
                # No resampling needed - direct passthrough
                with PWM._lock:
                    PWM._sample_buffer.append(val)
                    PWM._samples_out += 1
            else:
                # Resample using linear interpolation
                with PWM._lock:
                    # How many output samples does this input sample generate?
                    # Add the resampling ratio to our position
                    PWM._resample_position += PWM._resample_ratio

                    # Generate interpolated samples
                    while PWM._resample_position >= 1.0:
                        # Calculate interpolation factor
                        frac = 1.0 - (PWM._resample_position - PWM._resample_ratio) / PWM._resample_ratio
                        frac = max(0.0, min(1.0, frac))

                        # Linear interpolation between last and current sample
                        interpolated = int(PWM._last_input_sample + frac * (val - PWM._last_input_sample))
                        PWM._sample_buffer.append(interpolated)
                        PWM._samples_out += 1

                        PWM._resample_position -= 1.0

                    # Store current sample for next interpolation
                    PWM._last_input_sample = val

            # Debug output every 5 seconds
            current_time = time.time()
            if current_time - PWM._last_debug_time >= 5.0:
                with PWM._lock:
                    buffer_size = len(PWM._sample_buffer)
                elapsed = current_time - PWM._last_debug_time
                in_rate = PWM._samples_in / elapsed
                out_rate = PWM._samples_out / elapsed
                print(f"[Audio] Rates: in={in_rate:.0f} Hz, out={out_rate:.0f} Hz, buffer={buffer_size}, ratio={PWM._resample_ratio:.4f}")
                PWM._samples_in = 0
                PWM._samples_out = 0
                PWM._last_debug_time = current_time

    @staticmethod
    def _audio_player_thread():
        """Background thread that continuously plays audio from buffer"""
        chunk_size = 512  # Preferred chunk size
        min_chunk = 64   # Minimum chunk size - play smaller chunks when decoder is slow
        headroom = 8192  # Wait for this many samples before starting (~512ms buffer at 16kHz)
        chunks_played = 0
        small_chunk_count = 0
        playback_started = False

        print(f"[Audio] Playback thread starting, will wait for {headroom} samples (512ms) before playing", flush=True)

        while not PWM._stop_playback:
            # Check if we have enough samples to play
            with PWM._lock:
                buffer_size = len(PWM._sample_buffer)
                active_pwm = PWM._active_pwm  # Get current active PWM

            # If no active PWM, exit thread
            if active_pwm is None:
                print(f"[Audio] No active PWM, playback thread exiting", flush=True)
                break

            # Wait for buffer to fill before starting playback (reduces underruns)
            if not playback_started:
                if buffer_size >= headroom:
                    playback_started = True
                    print(f"[Audio] Buffer filled to {buffer_size} samples, starting playback", flush=True)
                else:
                    time.sleep(0.01)
                    continue

            # Extract chunk - play whatever is available (eliminates underruns)
            with PWM._lock:
                buffer_size = len(PWM._sample_buffer)
                if buffer_size >= min_chunk:
                    # Play whatever we have, up to chunk_size
                    actual_chunk_size = min(buffer_size, chunk_size)
                    chunk = PWM._sample_buffer[:actual_chunk_size]
                    PWM._sample_buffer = PWM._sample_buffer[actual_chunk_size:]

                    # Track small chunks (indicates decoder is slow)
                    if actual_chunk_size < chunk_size:
                        small_chunk_count += 1
                        if small_chunk_count <= 5 or small_chunk_count % 20 == 0:
                            print(f"[Audio] Small chunk #{small_chunk_count}: {actual_chunk_size} samples (buffer: {buffer_size})")
                else:
                    chunk = None

            if chunk and pygame:
                chunks_played += 1
                if chunks_played <= 3 or chunks_played % 100 == 0:
                    print(f"[Audio] Played chunk #{chunks_played}, buffer: {buffer_size} samples")
                try:
                    # Convert 16-bit unsigned (0-65535) to 16-bit signed (-32768 to 32767)
                    samples = np.array(chunk, dtype=np.int32)
                    samples_signed = (samples - 32768).astype(np.int16)

                    # Reshape for stereo if needed
                    mixer_info = pygame.mixer.get_init()
                    if mixer_info and mixer_info[2] == 2:  # If stereo
                        samples_stereo = np.column_stack((samples_signed, samples_signed))
                        sound = pygame.sndarray.make_sound(samples_stereo)
                    else:  # Mono
                        sound = pygame.sndarray.make_sound(samples_signed)

                    # Play sound - queue if channel is busy, otherwise start playback
                    if not PWM._channel.get_busy():
                        PWM._channel.play(sound)
                        if chunks_played <= 5:
                            print(f"[Audio] Started playback of chunk #{chunks_played}", flush=True)
                    else:
                        PWM._channel.queue(sound)

                except Exception as e:
                    if chunks_played <= 5:
                        print(f"[Audio] Error playing chunk: {e}", flush=True)
            else:
                # No chunk ready, sleep briefly
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
        while not self._stop_event.is_set():
            try:
                if self._callback:
                    self._callback(self)
            except:
                pass
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
