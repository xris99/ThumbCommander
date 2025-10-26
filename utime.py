"""
utime.py - PC implementation of MicroPython's utime module
"""
import time as _time

def ticks_ms():
    """Return millisecond counter"""
    return int(_time.time() * 1000)

def ticks_us():
    """Return microsecond counter"""
    return int(_time.time() * 1000000)

def ticks_diff(new, old):
    """Calculate difference between two ticks values"""
    # Handle wrap-around (MicroPython ticks wrap at varying values)
    diff = new - old
    # Simple implementation - assume 32-bit wrap
    if diff < 0:
        diff += (1 << 30)
    return diff

def sleep_ms(ms):
    """Sleep for ms milliseconds"""
    _time.sleep(ms / 1000.0)

def sleep_us(us):
    """Sleep for us microseconds"""
    _time.sleep(us / 1000000.0)

def sleep(seconds):
    """Sleep for seconds"""
    _time.sleep(seconds)
