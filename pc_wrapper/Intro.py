"""
Intro module stub for PC
The ThumbyColor version doesn't use this, but it's here for compatibility with original Thumby
"""

# Module state
_initialized = False
_running = False


def __init__():
    """Initialize intro"""
    global _initialized
    _initialized = True
    print("Intro: Initialized (PC version - no intro animation)")


def start():
    """Start intro"""
    global _running
    _running = True
    # On PC, we skip the intro since ThumbyColor shows its own intro
    print("Intro: Started (skipping for ThumbyColor)")


def finish():
    """Finish intro"""
    global _running
    _running = False
    print("Intro: Finished")
