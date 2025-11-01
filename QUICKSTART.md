# ThumbCommander PC Wrapper - Quick Start

## What Was Done

A complete PC wrapper has been created that allows the ThumbyColor version of ThumbCommander to run on PC using Python and pygame. **The game code is completely unchanged** - all compatibility is handled through wrapper modules.

## Installation

1. **Install Python 3.7+** if you don't have it already

2. **Install pygame**:
   ```bash
   pip install pygame
   ```

3. **Test the wrapper** (optional but recommended):
   ```bash
   python test_wrapper.py
   ```
   This will verify all components work correctly.

## Running the Game

Simply run:
```bash
python run_pc.py
```

Or on Linux/Mac:
```bash
chmod +x run_pc.py
./run_pc.py
```

## Controls

| Keyboard Key | Thumby Button     | Action           |
|--------------|-------------------|------------------|
| Arrow Keys   | D-Pad             | Move ship        |
| Z            | Button A          | Fire laser       |
| X            | Button B          | Secondary action |
| A            | Left Bumper (LB)  | Target previous  |
| S            | Right Bumper (RB) | Target next      |
| ESC          | Menu              | Menu/Pause       |

## How It Works

The wrapper creates a MicroPython-compatible environment:

1. **Module Injection**: Wrapper modules are inserted into `sys.modules` before the game starts
2. **MicroPython Emulation**: Decorators like `@micropython.viper` become no-ops
3. **Framebuffer**: Full RGB565 framebuffer implementation
4. **Display**: Pygame renders the framebuffer to a window (512x512)
5. **Input**: Keyboard events mapped to button states
6. **Game Logic**: Runs unchanged - all viper methods work as-is

## Troubleshooting

### ImportError: No module named 'pygame'
```bash
pip install pygame
```

### Game won't start
Run the test script first:
```bash
python test_wrapper.py
```

### No window appears
Make sure pygame is properly installed and your system supports OpenGL/SDL2.

### Keyboard not responding
Click on the game window to give it focus.

## What's Included

### Wrapper Modules (`pc_wrapper/`)
- `micropython_compat.py` - @viper/@native decorators as no-ops
- `framebuf.py` - FrameBuffer with RGB565 support
- `thumbycolor_native.py` - ColorDisplay and ColorSprite classes
- `thumbyButton.py` - Keyboard to button mapping
- `engine.py`, `engine_io.py` - ThumbyColor engine stubs
- `audio.py` - Audio system stub (no sound on PC)
- `utime.py`, `machine.py`, `gc_compat.py` - MicroPython modules
- And more...

### Scripts
- `run_pc.py` - Main launcher
- `test_wrapper.py` - Test suite to validate wrapper
- `requirements.txt` - Python dependencies

### Documentation
- `PC_README.md` - User guide
- `WRAPPER_IMPLEMENTATION.md` - Technical details
- `QUICKSTART.md` - This file

## Key Features

✅ **Zero game code changes** - All compatibility via wrapper
✅ **Full RGB565 support** - Proper color rendering
✅ **Sprite rendering** - Loads .COL.bin files with scaling/mirroring
✅ **All viper methods work** - Decorators are no-ops but code runs fine
✅ **Framebuffer blit** - HUD compositing works correctly
✅ **Platform detection** - Game detects as ThumbyColor

## Limitations

- **No audio** - Audio is stubbed (could be implemented with pygame.mixer)
- **No rumble** - Haptic feedback not available on PC
- **Performance** - Not representative of actual hardware
- **File paths** - Assumes game directory structure

## Testing Status

All wrapper components tested and working:
- ✓ MicroPython compatibility (const, viper, native)
- ✓ Framebuffer (RGB565, pixel ops, drawing primitives)
- ✓ Display module (requires pygame)
- ✓ Button module (requires pygame)
- ✓ Time functions (ticks_ms, ticks_us, etc.)
- ✓ All stub modules
- ✓ Platform detection

## Architecture Overview

```
User runs: python run_pc.py
    ↓
Sets up sys.path and sys.modules
    ↓
Imports pc_wrapper compatibility modules
    ↓
Game imports micropython, framebuf, etc.
    ↓
Gets PC-compatible versions from wrapper
    ↓
Game runs unchanged
    ↓
Display renders via pygame
    ↓
Keyboard events → button states
```

## Next Steps

To run the game with audio support, implement audio playback using pygame.mixer in `pc_wrapper/audio.py`.

To add gamepad support, extend `pc_wrapper/thumbyButton.py` to read from USB game controllers.

## Support

For issues or questions:
- Check `PC_README.md` for detailed usage
- Check `WRAPPER_IMPLEMENTATION.md` for technical details
- Run `python test_wrapper.py` to diagnose problems

---

**Note**: This wrapper is designed for the ThumbyColor version. The original Thumby (grayscale) version uses different modules and would need a separate wrapper.
