"""
MicroPython machine module for PC with audio support
Provides PWM and Timer that work with pygame for audio output
"""

import threading
import time
import os
import numpy as np

# Debug flag - set to True to see detailed audio diagnostics
DEBUG_AUDIO = True

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
                if DEBUG_AUDIO:
                    print(f"[Audio Debug] Mixer already initialized: freq={existing_init[0]}, size={existing_init[1]}, channels={existing_init[2]}")
                _audio_initialized = True
            else:
                # Initialize pygame.mixer for audio playback
                if DEBUG_AUDIO:
                    print("[Audio Debug] Initializing pygame.mixer at 16000 Hz mono")
                pygame.mixer.pre_init(frequency=16000, size=-16, channels=1, buffer=512)
                pygame.mixer.init()
                mixer_info = pygame.mixer.get_init()
                if DEBUG_AUDIO:
                    print(f"[Audio Debug] Mixer initialized: freq={mixer_info[0]}, size={mixer_info[1]}, channels={mixer_info[2]}")
                _audio_initialized = True
        except Exception as e:
            if DEBUG_AUDIO:
                print(f"[Audio Debug] Error initializing mixer: {e}")
            # Mixer initialization failed, but we can still continue
            # Audio just won't work
            _audio_initialized = True  # Don't keep trying
            return False

    return pygame is not None


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
    Collects 16-bit unsigned samples (0-65535) and plays them as continuous audio stream
    """

    # Class-level audio state
    _sample_buffer = []
    _sample_rate = 8000  # Default, will be updated
    _active_pwm = None
    _lock = threading.Lock()
    _playback_thread = None
    _stop_playback = False
    _channel = None
    _samples_received = 0
    _chunks_played = 0
    _last_sample_value = None

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

        if DEBUG_AUDIO:
            print(f"[Audio Debug] PWM.__init__ called: freq={freq} (PWM carrier frequency)")

        # Only set as active PWM if pygame is available
        if _ensure_pygame():
            with PWM._lock:
                # If there's already an active PWM, stop it
                if PWM._active_pwm is not None and PWM._active_pwm is not self:
                    if DEBUG_AUDIO:
                        print("[Audio Debug] Stopping previous PWM instance")
                    PWM._active_pwm._cleanup()

                PWM._active_pwm = self
                PWM._sample_buffer = []
                PWM._stop_playback = False
                PWM._samples_received = 0
                PWM._chunks_played = 0

                # Get a dedicated mixer channel for audio streaming
                if PWM._channel is None:
                    PWM._channel = pygame.mixer.Channel(0)
                    if DEBUG_AUDIO:
                        print(f"[Audio Debug] Created mixer channel 0")

                # Start playback thread if not running
                if PWM._playback_thread is None or not PWM._playback_thread.is_alive():
                    if DEBUG_AUDIO:
                        print("[Audio Debug] Starting audio playback thread")
                    PWM._playback_thread = threading.Thread(target=self._audio_player_thread, daemon=True)
                    PWM._playback_thread.start()

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
        """
        if val is None:
            return self._duty

        self._duty = val

        # Send sample to audio buffer if we're the active PWM
        if PWM._active_pwm is self:
            with PWM._lock:
                PWM._sample_buffer.append(val)
                PWM._samples_received += 1

                # Debug: First few samples and detect sample rate
                if DEBUG_AUDIO:
                    if PWM._samples_received <= 3:
                        print(f"[Audio Debug] Sample #{PWM._samples_received}: value={val}")
                    elif PWM._samples_received == 1000:
                        print(f"[Audio Debug] Received 1000 samples, buffer size: {len(PWM._sample_buffer)}")
                        # Try to detect sample rate from timing
                        import sys
                        try:
                            # Access audio module to get sample rate
                            if 'audio' in sys.modules:
                                audio_mod = sys.modules['audio']
                                if hasattr(audio_mod, 'audio') and hasattr(audio_mod.audio, 'sample_rate'):
                                    detected_rate = audio_mod.audio.sample_rate
                                    mixer_rate = pygame.mixer.get_init()[0]
                                    print(f"[Audio Debug] Audio file sample rate: {detected_rate} Hz")
                                    print(f"[Audio Debug] Pygame mixer rate: {mixer_rate} Hz")
                                    if detected_rate != mixer_rate:
                                        print(f"[Audio Debug] **WARNING** Sample rate mismatch! Audio will play at wrong speed!")
                                        print(f"[Audio Debug] Speed ratio: {mixer_rate/detected_rate:.2f}x")
                        except:
                            pass

    @staticmethod
    def _audio_player_thread():
        """Background thread that continuously plays audio from buffer"""
        chunk_size = 1024  # Samples per chunk

        if DEBUG_AUDIO:
            print(f"[Audio Debug] Audio player thread started, chunk_size={chunk_size}")

        while not PWM._stop_playback:
            # Check if we have enough samples to play
            with PWM._lock:
                if len(PWM._sample_buffer) >= chunk_size:
                    # Extract chunk
                    chunk = PWM._sample_buffer[:chunk_size]
                    PWM._sample_buffer = PWM._sample_buffer[chunk_size:]
                else:
                    chunk = None

            if chunk and pygame:
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

                    # Debug sound properties
                    if DEBUG_AUDIO and PWM._chunks_played < 2:
                        print(f"[Audio Debug] Chunk #{PWM._chunks_played + 1}:")
                        print(f"  - Sample values: min={samples_signed.min()}, max={samples_signed.max()}, mean={samples_signed.mean():.1f}")
                        print(f"  - Sound length: {sound.get_length():.3f}s ({len(chunk)} samples)")
                        print(f"  - Channel queue status: {PWM._channel.get_queue()}")
                        print(f"  - Channel playing: {PWM._channel.get_busy()}")

                    # Queue sound on dedicated channel
                    if PWM._channel.get_queue() is None:
                        PWM._channel.play(sound)
                        if DEBUG_AUDIO and PWM._chunks_played < 2:
                            print(f"  - Action: play() on empty channel")
                    else:
                        PWM._channel.queue(sound)
                        if DEBUG_AUDIO and PWM._chunks_played < 2:
                            print(f"  - Action: queue() on active channel")

                    PWM._chunks_played += 1
                    if DEBUG_AUDIO and PWM._chunks_played % 50 == 0:
                        print(f"[Audio Debug] Played {PWM._chunks_played} chunks, buffer: {len(PWM._sample_buffer)} samples")

                except Exception as e:
                    if DEBUG_AUDIO:
                        print(f"[Audio Debug] Error playing chunk: {e}")
                        import traceback
                        traceback.print_exc()
            else:
                # No chunk ready, sleep briefly
                time.sleep(0.01)

        if DEBUG_AUDIO:
            print("[Audio Debug] Audio player thread exiting")

    def _cleanup(self):
        """Stop audio playback"""
        if DEBUG_AUDIO:
            print(f"[Audio Debug] PWM._cleanup(): received {PWM._samples_received} samples, played {PWM._chunks_played} chunks")
        with PWM._lock:
            PWM._sample_buffer = []
            if PWM._channel:
                PWM._channel.stop()

    def deinit(self):
        """Deinitialize PWM"""
        if DEBUG_AUDIO:
            print("[Audio Debug] PWM.deinit() called")
        if PWM._active_pwm is self:
            self._cleanup()
            with PWM._lock:
                PWM._active_pwm = None


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

        if DEBUG_AUDIO and callback:
            print(f"[Audio Debug] Timer.init: mode={'PERIODIC' if mode == Timer.PERIODIC else 'ONE_SHOT'}, period={self._period_ms:.1f}ms")

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
