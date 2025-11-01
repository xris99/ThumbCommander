#!/usr/bin/env python3
"""Test pygame key detection"""
import os
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import pygame
pygame.init()

screen = pygame.display.set_mode((400, 300))
pygame.display.set_caption("Key Test")
font = pygame.font.Font(None, 24)

print("Press keys to test detection (10 seconds)")
print("Try: arrows, Z, X, Q, W, ESC")

import time
start = time.time()
last_keys = set()

while time.time() - start < 10:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            break
        if event.type == pygame.KEYDOWN:
            key_name = pygame.key.name(event.key)
            print(f"  Key pressed: {key_name} (code: {event.key})")

    keys = pygame.key.get_pressed()
    current_keys = set()

    # Check specific keys
    if keys[pygame.K_UP]:
        current_keys.add("UP")
    if keys[pygame.K_DOWN]:
        current_keys.add("DOWN")
    if keys[pygame.K_LEFT]:
        current_keys.add("LEFT")
    if keys[pygame.K_RIGHT]:
        current_keys.add("RIGHT")
    if keys[pygame.K_z]:
        current_keys.add("Z")
    if keys[pygame.K_x]:
        current_keys.add("X")
    if keys[pygame.K_q]:
        current_keys.add("Q")
    if keys[pygame.K_w]:
        current_keys.add("W")
    if keys[pygame.K_ESCAPE]:
        current_keys.add("ESC")
        break

    # Draw current state
    screen.fill((0, 0, 0))
    y = 20
    text = font.render("Keys currently pressed:", True, (255, 255, 255))
    screen.blit(text, (10, y))
    y += 30

    if current_keys:
        for key in current_keys:
            text = font.render(key, True, (0, 255, 0))
            screen.blit(text, (20, y))
            y += 25
    else:
        text = font.render("(none)", True, (128, 128, 128))
        screen.blit(text, (20, y))

    pygame.display.flip()
    pygame.time.Clock().tick(30)

pygame.quit()
print("\nKey test complete")
