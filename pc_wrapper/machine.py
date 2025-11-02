"""
MicroPython machine module for PC with audio support
Provides PWM and Timer that work with pygame for audio output
"""

import threading
import time
import os
import numpy as np

# Set dummy audio driver for headless environments (only if explicitly requested)
# User can set SDL_AUDIODRIVER=dummy to force dummy mode
# Otherwise, pygame will try to use available audio hardware

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
            if not _audio_initialized and pygame:
                # Initialize pygame.mixer for audio playback
                # Use 16000 Hz to support common Thumby audio rates
                pygame.mixer.pre_init(frequency=16000, size=-16, channels=1, buffer=512)
                pygame.mixer.init()
                _audio_initialized = True
        except ImportError:
            pass
    return pygame is not None


def freq(frequency=None):
    """Get or set CPU frequency - no-op on PC"""
    if frequency is None:
        return 200_000_000  # Return a dummy frequency
    # Setting frequency is a no-op on PC
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
    _sample_rate = 8000  # Will be set based on actual audio
    _active_pwm = None
    _lock = threading.Lock()
    _playback_thread = None
    _stop_playback = False
    _channel = None

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
        if _ensure_pygame():
            with PWM._lock:
                # If there's already an active PWM, stop it
                if PWM._active_pwm is not None and PWM._active_pwm is not self:
                    PWM._active_pwm._cleanup()

                PWM._active_pwm = self
                PWM._sample_buffer = []
                PWM._stop_playback = False

                # Get a dedicated mixer channel for audio streaming
                if PWM._channel is None:
                    PWM._channel = pygame.mixer.Channel(0)

                # Start playback thread if not running
                if PWM._playback_thread is None or not PWM._playback_thread.is_alive():
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

    @staticmethod
    def _audio_player_thread():
        """Background thread that continuously plays audio from buffer"""
        chunk_size = 1024  # Samples per chunk

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
                    # Must subtract 32768 as int32 first, then convert to int16
                    samples = np.array(chunk, dtype=np.int32)  # Use int32 to avoid overflow
                    samples_signed = (samples - 32768).astype(np.int16)  # Subtract then convert

                    # Reshape for stereo if needed (duplicate mono channel)
                    mixer_info = pygame.mixer.get_init()
                    if mixer_info and mixer_info[2] == 2:  # If stereo (2 channels)
                        # Duplicate mono to stereo
                        samples_stereo = np.column_stack((samples_signed, samples_signed))
                        sound = pygame.sndarray.make_sound(samples_stereo)
                    else:  # Mono
                        sound = pygame.sndarray.make_sound(samples_signed)

                    # Queue sound on dedicated channel for seamless playback
                    if PWM._channel.get_queue() is None:
                        # Channel is empty, play immediately
                        PWM._channel.play(sound)
                    else:
                        # Queue for seamless continuation
                        PWM._channel.queue(sound)
                except:
                    pass  # Silently fail if audio has issues
            else:
                # No chunk ready, sleep briefly
                time.sleep(0.01)

    def _cleanup(self):
        """Stop audio playback"""
        with PWM._lock:
            PWM._sample_buffer = []
            if PWM._channel:
                PWM._channel.stop()

    def deinit(self):
        """Deinitialize PWM"""
        if PWM._active_pwm is self:
            self._cleanup()
            with PWM._lock:
                PWM._active_pwm = None


class Timer:
    """
    Timer class that actually works for callbacks
    Used by audio.py for buffer filling
    """
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
        """
        Initialize timer

        Args:
            mode: PERIODIC or ONE_SHOT
            period: Period in milliseconds
            freq: Frequency in Hz (alternative to period)
            callback: Callback function
        """
        # Stop existing timer
        self.deinit()

        self._callback = callback
        self._mode = mode

        # Calculate period
        if period is not None:
            self._period_ms = period
        elif freq is not None:
            self._period_ms = 1000.0 / freq
        else:
            self._period_ms = 100  # Default 100ms

        if callback is not None:
            self._stop_event = threading.Event()

            if mode == Timer.PERIODIC:
                self._thread = threading.Thread(target=self._periodic_worker, daemon=True)
            else:  # ONE_SHOT
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

            # Sleep for period, but check stop event frequently
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
