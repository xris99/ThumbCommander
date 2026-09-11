"""
MicroPython machine module for PC
Provides Pin, Timer, and SPI stubs for hardware compatibility
Audio is handled by pc_wrapper/audio.py (no PWM emulation needed)
"""

import threading
import time


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


class Timer:
    """Timer class for periodic/one-shot callbacks"""
    PERIODIC = 0
    ONE_SHOT = 1

    def __init__(self):
        self._timer = None
        self._callback = None
        self._mode = None

    def init(self, mode=PERIODIC, freq=None, period=None, callback=None):
        """Initialize timer

        Args:
            mode: Timer.PERIODIC or Timer.ONE_SHOT
            freq: Frequency in Hz (alternative to period)
            period: Period in milliseconds
            callback: Callback function(timer)
        """
        self._mode = mode
        self._callback = callback

        # Calculate period from freq or use period directly
        if freq is not None:
            period_seconds = 1.0 / freq
        elif period is not None:
            period_seconds = period / 1000.0
        else:
            period_seconds = 1.0

        # Stop existing timer
        if self._timer:
            self._timer.cancel()

        # Start new timer
        if mode == Timer.PERIODIC:
            self._start_periodic(period_seconds)
        else:  # ONE_SHOT
            self._start_oneshot(period_seconds)

    def _start_periodic(self, period):
        """Start periodic timer"""
        def tick():
            if self._callback:
                self._callback(self)
            if self._mode == Timer.PERIODIC:
                self._timer = threading.Timer(period, tick)
                self._timer.daemon = True
                self._timer.start()

        self._timer = threading.Timer(period, tick)
        self._timer.daemon = True
        self._timer.start()

    def _start_oneshot(self, period):
        """Start one-shot timer"""
        def tick():
            if self._callback:
                self._callback(self)

        self._timer = threading.Timer(period, tick)
        self._timer.daemon = True
        self._timer.start()

    def deinit(self):
        """Stop and deinitialize timer"""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._callback = None


class SPI:
    """SPI stub for hardware compatibility"""
    MSB = 0
    LSB = 1

    def __init__(self, id, baudrate=1000000, polarity=0, phase=0, bits=8, firstbit=MSB, sck=None, mosi=None, miso=None):
        self.id = id
        self.baudrate = baudrate
        self.polarity = polarity
        self.phase = phase
        self.bits = bits
        self.firstbit = firstbit

    def init(self, baudrate=1000000, polarity=0, phase=0, bits=8, firstbit=MSB):
        self.baudrate = baudrate
        self.polarity = polarity
        self.phase = phase
        self.bits = bits
        self.firstbit = firstbit

    def deinit(self):
        pass

    def write(self, data):
        pass

    def read(self, nbytes, write=0x00):
        return bytes(nbytes)

    def readinto(self, buf, write=0x00):
        pass

    def write_readinto(self, write_buf, read_buf):
        pass
