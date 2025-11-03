"""
MicroPython utime module compatibility for PC
"""

import time as _time

# Use high-precision monotonic timer for microsecond accuracy
# perf_counter_ns() has nanosecond precision, critical for audio timing
_start_time_ns = _time.perf_counter_ns()

# MicroPython's ticks_us() wraps at 2^30 microseconds (~17.9 minutes)
# This is critical for @viper mode's 32-bit integer arithmetic
_TICKS_MAX = 0x3FFFFFFF  # 2^30 - 1
_TICKS_PERIOD = 0x40000000  # 2^30


def ticks_ms():
    """Get millisecond counter with microsecond precision and wrapping"""
    elapsed_ns = _time.perf_counter_ns() - _start_time_ns
    ms = (elapsed_ns // 1_000_000) & _TICKS_MAX
    return int(ms)


def ticks_us():
    """Get microsecond counter with nanosecond precision and wrapping at 2^30"""
    elapsed_ns = _time.perf_counter_ns() - _start_time_ns
    us = (elapsed_ns // 1_000) & _TICKS_MAX
    return int(us)


def ticks_diff(end, start):
    """
    Calculate difference between two tick values, handling wrapping.
    Returns the signed difference modulo the tick period.
    """
    diff = (end - start) & _TICKS_MAX
    # Handle sign: if diff > 2^29, it's actually a negative difference
    if diff & 0x20000000:  # Check bit 29 (half of period)
        diff -= _TICKS_PERIOD
    return diff


def ticks_add(ticks, delta):
    """Add delta to ticks value with wrapping"""
    return (ticks + delta) & _TICKS_MAX


def sleep(seconds):
    """Sleep for seconds"""
    _time.sleep(seconds)


def sleep_ms(milliseconds):
    """Sleep for milliseconds"""
    _time.sleep(milliseconds / 1000.0)


def sleep_us(microseconds):
    """Sleep for microseconds"""
    _time.sleep(microseconds / 1000000.0)


def time():
    """Get current time in seconds since epoch"""
    return int(_time.time())


def monotonic():
    """Get monotonic time in seconds"""
    return _time.monotonic()


def localtime(secs=None):
    """Convert seconds to local time tuple"""
    return _time.localtime(secs)


def gmtime(secs=None):
    """Convert seconds to UTC time tuple"""
    return _time.gmtime(secs)
