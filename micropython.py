"""
micropython.py - PC stub for MicroPython's micropython module
Provides decorators and const function for PC compatibility
"""

def const(x):
    """
    Declare a constant value (no-op on PC)
    On MicroPython, this allows the compiler to optimize the value
    """
    return x

def native(func):
    """
    Decorator to compile function to native code (no-op on PC)
    """
    return func

def viper(func):
    """
    Decorator to compile function with viper code emitter (no-op on PC)
    """
    return func

def asm_thumb(func):
    """
    Decorator for inline assembler (no-op on PC)
    """
    return func

def opt_level(level):
    """
    Set optimization level (no-op on PC)
    """
    pass

def mem_info(verbose=False):
    """
    Print memory info (stub on PC)
    """
    print("Memory info not available on PC")

def qstr_info(verbose=False):
    """
    Print qstr info (stub on PC)
    """
    pass

def stack_use():
    """
    Return stack usage (stub on PC)
    """
    return 0

def heap_lock():
    """
    Lock the heap (no-op on PC)
    """
    pass

def heap_unlock():
    """
    Unlock the heap (no-op on PC)
    """
    pass

def kbd_intr(chr):
    """
    Set keyboard interrupt character (no-op on PC)
    """
    pass

def schedule(func, arg):
    """
    Schedule function to be executed (simplified on PC)
    """
    func(arg)

def ptr32(obj):
    """
    Return pointer to 32-bit array (viper mode)
    On PC, just return the object itself
    """
    return obj

def ptr16(obj):
    """
    Return pointer to 16-bit array (viper mode)
    On PC, just return the object itself
    """
    return obj

def ptr8(obj):
    """
    Return pointer to 8-bit array (viper mode)
    On PC, just return the object itself
    """
    return obj
