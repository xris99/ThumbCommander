#!/usr/bin/env python3
"""
quick_test.py - Quick interactive test of pygame functionality
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import pygame platform
import pygame_platform
import pygame

print("=" * 60)
print("Quick Interactive Test")
print("=" * 60)
print("Testing: Button Input + Sprite Rendering + Display")
print()
print("Controls:")
print("  Y = Fire button")
print("  Arrow Keys = Movement")
print("  ESC = Quit")
print("=" * 60)
print()

# Create display
display = pygame_platform.display
display.setFPS(60)

# Test sprites
test_sprite_enemy = pygame_platform.PygameSprite(70, 59, "enemy1_test.bin", 30, 30)
test_sprite_asteroid = pygame_platform.PygameSprite(56, 47, "astroid1_test.bin", 100, 30)

frame = 0
running = True

print("Test running - window should appear")
print("Press Y to see button feedback")
print("Press ESC to quit")
print()

while running:
    frame += 1

    # Clear screen
    display.fill(display.BLACK)

    # Draw gradient background
    for i in range(128):
        blue_val = int(10 + (i / 128) * 30)
        pygame.draw.line(display.internal_fb, (0, 0, blue_val), (0, i), (128, i))

    # Draw title
    display.drawText("ThumbCommander Test", 10, 10, display.WHITE)
    display.drawText(f"Frame: {frame}", 10, 25, display.LIGHTGRAY)

    # Draw sprites
    test_sprite_enemy.draw(display)
    test_sprite_asteroid.draw(display)

    # Test buttons
    y = 45
    if pygame_platform.buttonA.pressed():
        display.drawText("Y (FIRE) PRESSED!", 10, y, display.RED)
        y += 15
        print(f"Frame {frame}: Y button pressed")

    if pygame_platform.buttonU.pressed():
        display.drawText("UP PRESSED", 10, y, display.BLUE)
        y += 15

    if pygame_platform.buttonD.pressed():
        display.drawText("DOWN PRESSED", 10, y, display.BLUE)
        y += 15

    if pygame_platform.buttonL.pressed():
        display.drawText("LEFT PRESSED", 10, y, display.BLUE)
        y += 15

    if pygame_platform.buttonR.pressed():
        display.drawText("RIGHT PRESSED", 10, y, display.BLUE)
        y += 15

    # Check for quit
    if pygame_platform.buttonMENU.justPressed():
        print("ESC pressed - quitting")
        running = False

    # Draw animated box
    box_x = 10 + int(100 * ((frame % 120) / 120.0))
    display.drawFilledRectangle(box_x, 100, 15, 15, display.ORANGE)

    # Status
    display.drawText("Press buttons to test", 10, 115, display.LIGHTGRAY)

    # Update display
    display.update()

print("\nTest completed!")
print("If you saw graphics and button presses registered, everything works!")
