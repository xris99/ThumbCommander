# ThumbCommander - PC Edition

This wrapper allows you to run the ThumbyColor version of ThumbCommander on your PC using Python and pygame.

## Features

- Complete ThumbyColor game experience on PC
- No modifications to the original game code
- All game logic runs through wrapper modules
- RGB565 framebuffer emulation
- Keyboard controls mapped to Thumby buttons

## Requirements

- Python 3.7 or higher
- pygame 2.0 or higher

## Installation

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the game:
   ```bash
   python run_pc.py
   ```

   Or make it executable (Linux/Mac):
   ```bash
   chmod +x run_pc.py
   ./run_pc.py
   ```

## Controls

| Keyboard Key | Thumby Button |
|--------------|---------------|
| Arrow Keys   | D-Pad         |
| Z            | Button A (Fire)|
| X            | Button B      |
| A            | Left Bumper   |
| S            | Right Bumper  |
| ESC          | Menu          |

## How It Works

The wrapper creates a compatibility layer that:

1. **MicroPython Emulation**: Provides decorators like `@micropython.viper` and `@micropython.native` as no-ops
2. **Framebuffer**: Implements MicroPython's `framebuf.FrameBuffer` with RGB565 support
3. **Display**: Uses pygame to render the framebuffer to a window
4. **Input**: Maps keyboard keys to button states
5. **Hardware Stubs**: Provides dummy implementations for audio, rumble, etc.

All game code runs unchanged - the wrapper injects compatibility modules before the game starts.

## Technical Details

### Wrapper Architecture

```
run_pc.py (launcher)
    └── Sets up sys.path and sys.modules
    └── Imports pc_wrapper modules
    └── Runs ThumbCommander.py

pc_wrapper/
    ├── micropython_compat.py    # @viper, @native decorators
    ├── framebuf.py              # FrameBuffer with RGB565
    ├── thumbycolor_native.py    # Display & Sprite classes
    ├── thumbyButton.py          # Button input handling
    ├── engine.py                # Engine module stub
    ├── engine_io.py             # IO constants
    ├── audio.py                 # Audio stubs
    ├── utime.py                 # Time functions
    ├── machine.py               # Machine module
    └── ...
```

### RGB565 Format

The ThumbyColor uses RGB565 format (16-bit color):
- 5 bits red (0-31)
- 6 bits green (0-63)
- 5 bits blue (0-31)

The wrapper's framebuffer correctly handles this format and converts it to RGB888 for pygame rendering.

### Viper Methods

The game uses `@micropython.viper` decorated functions for performance. On PC, these decorators are no-ops, but the code runs correctly in standard Python.

## Limitations

- Audio playback is stubbed (no sound on PC)
- Rumble/haptic feedback is disabled
- Some visual effects may look different
- Performance is not representative of hardware

## Troubleshooting

### ImportError: No module named 'pygame'
Install pygame: `pip install pygame`

### Game window doesn't appear
Make sure pygame is properly installed and your system supports OpenGL/SDL2

### Keyboard not responding
Click on the game window to ensure it has focus

## License

This wrapper is provided as-is for running ThumbCommander on PC. The game code remains unchanged and retains its original license.
