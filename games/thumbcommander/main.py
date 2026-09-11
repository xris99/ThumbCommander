from sys import path

# Path bootstrap. The original Thumby firmware runs the entry script
# with the current directory at the littlefs ROOT, so relative paths
# (imports through ".", "assets/...", the campaign JSON files) do not
# resolve there - that was the ENOENT boot crash. The ThumbyColor
# firmware and the PC bootstrap already start inside the game
# directory. Only on the original Thumby do we move into the game
# directory, so all relative asset paths behave identically on all
# three targets (no hard-coded device paths in the game code).
try:
    import engine_io  # provided by the ThumbyColor firmware and the PC
except ImportError:
    import os
    try:
        os.chdir("/Games/ThumbCommander")
    except BaseException as e:
        print("WARN chdir:", type(e).__name__)
path.insert(0, '.')

# v3 - hardened diagnostics. The firmware's top-level handler only
# prints "Script error... :(", and on the 192KB Thumby heap an
# f-string in the handler below can itself OOM (that is what v1's
# silence proved). Every diagnostic here is therefore a literal
# string or an int (no allocation) and each print is individually
# guarded, so at least the exception class and the free-RAM figure
# survive even a completely exhausted heap.
print("SHIM v3")
try:
    import MainGame
except BaseException as e:
    try:
        import sys
        from gc import mem_free
        print("ERR", type(e).__name__)
        print("FREE", mem_free())
    except BaseException:
        pass
    try:
        # sys.print_exception exists in MicroPython (not in modern
        # CPython); the guard covers both.
        sys.print_exception(e)
    except BaseException:
        pass
    raise
