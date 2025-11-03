"""
MicroPython utime module compatibility for PC with high-precision timing
"""

import time as _time

# Use perf_counter for high-precision timing (nanosecond resolution)
# Store base time to ensure we have a consistent reference point
_base_time = _time.perf_counter()


def ticks_ms():
    """
    Get millisecond counter with high precision
    Uses perf_counter() which has nanosecond resolution on most systems
    """
    return int((_time.perf_counter() - _base_time) * 1000)


def ticks_us():
    """
    Get microsecond counter with high precision
    CRITICAL: Uses perf_counter() instead of time() for true microsecond precision
    time.time() only has ~1ms precision, but audio at 15625Hz needs 64µs precision
    """
    return int((_time.perf_counter() - _base_time) * 1000000)


def ticks_diff(end, start):
    """Calculate difference between two tick values"""
    return end - start


def ticks_add(ticks, delta):
    """Add delta to ticks value"""
    return ticks + delta


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
