"""
Quick test that skips the intro cutscene
"""
import os
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# Import ThumbCommander but skip intro
from platform_loader import display, IS_THUMBY_COLOR, Sprite, PC, create_sprite, buttonA, buttonB, buttonU, buttonD, buttonL, buttonR, buttonMENU
import sys

print(f"Platform: {'ThumbyColor' if IS_THUMBY_COLOR else 'Thumby'}")
print(f"Display: {display}")
print(f"Resolution: {PC.WIDTH}x{PC.HEIGHT}")

# Test basic display operations
print("Testing display.fill...")
display.fill(PC.BLACK)
display.update()

print("Testing drawing...")
display.fill(PC.BLUE)
display.drawFilledRectangle(10, 10, 50, 50, PC.WHITE)
display.drawText("HELLO", 20, 20, PC.RED)
display.update()

print("Waiting for button press...")
frame_count = 0
while frame_count < 300:  # 5 seconds at 60 FPS
    if buttonMENU.justPressed():
        print("Menu button pressed!")
        break
    if buttonA.justPressed():
        print("A button pressed!")
    if buttonU.justPressed():
        print("Up button pressed!")

    # Draw something each frame
    display.fill(PC.BLACK)
    display.drawText(f"Frame: {frame_count}", 10, 10, PC.WHITE)
    display.drawFilledRectangle(frame_count % PC.WIDTH, 50, 10, 10, PC.GREEN)
    display.update()

    frame_count += 1

print(f"Test complete! Rendered {frame_count} frames")
