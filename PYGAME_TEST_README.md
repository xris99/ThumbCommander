# ThumbCommander Pygame Test Harness

This directory contains a pygame-based test harness that allows running ThumbCommander on a PC for development and testing, without requiring actual Thumby or ThumbyColor hardware.

## Overview

The test harness creates a wrapper layer that mimics the ThumbyColor API using pygame, allowing the game code to run unmodified on a desktop computer.

## Architecture

### Files

- **`pygame_platform.py`** - Core pygame wrapper that mimics ThumbyColor APIs
  - `PygameDisplay` class - Emulates ColorDisplay with 128x128 RGB565 display
  - `PygameSprite` class - Emulates ColorSprite
  - Button classes - Maps keyboard to Thumby buttons
  - Audio stubs - Placeholder implementations

- **`test_pygame.py`** - Main test harness and launcher
  - Mocks micropython, hardware modules
  - Sets up the environment
  - Loads and runs the game
  - Includes built-in test mode

## Requirements

```bash
# Python 3.7+
pip install pygame
```

## Controls

| Thumby Button | Keyboard Key |
|--------------|--------------|
| D-Pad Up     | Arrow Up     |
| D-Pad Down   | Arrow Down   |
| D-Pad Left   | Arrow Left   |
| D-Pad Right  | Arrow Right  |
| A Button     | Z Key        |
| B Button     | X Key        |
| LB Button    | A Key        |
| RB Button    | S Key        |
| Menu         | ESC Key      |

## Running the Test

### Basic Test Mode

```bash
cd /home/user/ThumbCommander
python3 test_pygame.py
```

This will:
1. Initialize the pygame window (512x512, scaled 4x)
2. Run a basic test showing:
   - Display functionality
   - Button input
   - Animation
   - Heat level simulation
3. Press ESC to exit

### Display Features

The pygame wrapper provides:
- **128x128 resolution** (ThumbyColor size)
- **4x scaling** for visibility (512x512 window)
- **RGB565 to RGB888 color conversion**
- **60 FPS target** (configurable)

## Implementation Details

### Color Conversion

RGB565 colors from the game are automatically converted to RGB888 for pygame:

```python
def rgb565_to_rgb888(rgb565):
    r = ((rgb565 >> 11) & 0x1F) * 255 // 31
    g = ((rgb565 >> 5) & 0x3F) * 255 // 63
    b = (rgb565 & 0x1F) * 255 // 31
    return (r, g, b)
```

### Button System

Buttons are updated each frame and provide the same API as ThumbyButton:

```python
button.pressed()      # Returns True if currently pressed
button.justPressed()  # Returns True once per press
```

### Display API Compatibility

The `PygameDisplay` class implements all ThumbyColor display methods:
- `fill(color)` - Fill screen
- `setPixel(x, y, color)` - Draw pixel
- `drawLine(...)` - Draw line
- `drawRectangle(...)` - Draw rectangle outline
- `drawFilledRectangle(...)` - Draw filled rectangle
- `drawText(...)` - Render text
- `drawSprite(...)` - Draw sprite
- `update()` - Refresh display and handle events

### Sprite System

Sprites are rendered as simple colored rectangles for testing:
- Enemy sprites: Red tint
- Asteroid sprites: Brown tint
- Shield sprites: Blue tint

For full game testing, sprite loading would need to be implemented.

## Testing New Features

### Weapon Heat System

The test mode includes a heat visualization:
- 5 bars displayed at bottom
- Fills from left to right
- Red when filled, gray when empty
- Simulates the actual heat display

### Lead Targeting

To test enemy AI lead targeting:
1. Implement full game loading (requires asset files)
2. Start "Dog Fight" mode
3. Move predictably to see enemies predict your path
4. Move erratically to see them miss

## Limitations

### Current Limitations

1. **Sprite Assets** - Uses placeholder colored rectangles instead of actual sprites
2. **Audio** - Stubbed out (no sound)
3. **Cutscenes** - Skipped
4. **File I/O** - Game assets (.COL.bin files) not loaded

### Why These Limitations Exist

The test harness focuses on:
- Core game logic
- Display rendering
- Input handling
- Game mechanics (heat system, AI targeting)

Asset loading would require:
- Converting .COL.bin format to pygame surfaces
- Implementing frame-based sprite sheets
- Audio file format conversion

## Extending the Test Harness

### Loading Full Game

To run the complete game:

1. **Add Asset Loaders**
   ```python
   def load_col_sprite(filename):
       # Parse .COL.bin format
       # Return pygame Surface
       pass
   ```

2. **Implement Sprite Frames**
   ```python
   class PygameSprite:
       def __init__(self, ...):
           self.frames = load_all_frames(bitmap_data)

       def setFrame(self, frame):
           self.current_surface = self.frames[frame]
   ```

3. **Add Audio Support**
   ```python
   import pygame.mixer

   def audio_play_id(sound_id):
       sounds[sound_id].play()
   ```

### Adding Debug Features

Add these to `test_pygame.py` for debugging:

```python
# Show FPS
fps_text = f"FPS: {int(display.clock.get_fps())}"
display.drawText(fps_text, 10, HEIGHT-10, display.WHITE)

# Show enemy count
enemy_text = f"Enemies: {len(enemies.enemies)}"
display.drawText(enemy_text, 10, 30, display.LIGHTGRAY)

# Show weapon heat
heat_text = f"Heat: {ship.weapon_heat}/100"
display.drawText(heat_text, 10, 40, display.YELLOW)
```

## Validation Tests

### Test Checklist

Run through this checklist when testing:

- [ ] Window opens at 512x512 resolution
- [ ] Display renders at 60 FPS
- [ ] All keyboard controls respond
- [ ] Text rendering works
- [ ] Rectangle drawing works
- [ ] Pixel drawing works
- [ ] Colors display correctly
- [ ] Button press detection works
- [ ] Button release detection works
- [ ] ESC quits cleanly

### Performance Testing

Monitor performance with:
```python
import cProfile
cProfile.run('main_game_loop()', 'profile_stats')

import pstats
p = pstats.Stats('profile_stats')
p.sort_stats('cumulative').print_stats(20)
```

## Troubleshooting

### "No module named pygame"
```bash
pip install pygame
```

### "Cannot connect to X server"
If running on a headless system:
```bash
# Set SDL to use dummy video driver
export SDL_VIDEODRIVER=dummy
python3 test_pygame.py
```

### Import errors
Ensure all mock modules are loaded before importing game code:
```python
# Check module load order in test_pygame.py
# micropython must be mocked first
# Then hardware modules
# Then platform modules
```

### Display issues
- Check scale factor (SCALE_FACTOR in pygame_platform.py)
- Verify color conversion (test with known colors)
- Check coordinate ranges (0-127 for 128x128 display)

## Development Workflow

### Recommended Workflow

1. **Make changes to game code** (ThumbCommander.py, etc.)
2. **Run test harness** (`python3 test_pygame.py`)
3. **Verify functionality** visually
4. **Add validation tests** for new features
5. **Deploy to actual hardware** for final testing

### Benefits

- **Faster iteration** - No need to transfer to device
- **Better debugging** - Full Python stack traces
- **Visual testing** - See exactly what's rendered
- **Input testing** - Easy to test button combinations

## Future Enhancements

Potential improvements:
- [ ] Full sprite asset loading from .COL.bin files
- [ ] Audio playback support
- [ ] Save/load game state
- [ ] Record/playback input for regression testing
- [ ] Screenshot capture
- [ ] Performance profiling overlay
- [ ] Memory usage tracking
- [ ] Network multiplayer testing

## Credits

Created as a development tool for ThumbCommander to enable PC-based testing of game mechanics, particularly:
- Predictive lead targeting AI system
- Weapon heat management system
- Combat balance tuning
- Performance optimization

## License

Same as ThumbCommander main project.
