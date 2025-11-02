"""
MicroPython utime module compatibility for PC
"""

import time as _time


def ticks_ms():
    """Get millisecond counter"""
    return int(_time.time() * 1000)


def ticks_us():
    """Get microsecond counter"""
    return int(_time.time() * 1000000)


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
