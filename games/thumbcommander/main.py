from sys import path
try:
    import engine_io  # provided by the ThumbyColor firmware and the PC
except ImportError:
    import os
    try:
        os.chdir("/Games/ThumbCommander")
    except BaseException as e:
        print("WARN chdir:", type(e).__name__)
path.insert(0, '.')


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
        sys.print_exception(e)
    except BaseException:
        pass
    raise
