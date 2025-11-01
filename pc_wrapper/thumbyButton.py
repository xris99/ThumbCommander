"""
Thumby button emulation for PC
Maps keyboard keys to button states
"""

import pygame


class ButtonState:
    """
    Tracks button state for keyboard mapping
    """
    def __init__(self):
        self.current = False
        self.previous = False
        self.just_pressed = False


class ButtonClass:
    """
    Button class compatible with Thumby button API
    Maps to keyboard keys via pygame
    """

    # Class-level button states for all buttons
    button_states = {}

    # Keyboard mapping
    key_mapping = {
        'A': pygame.K_z,
        'B': pygame.K_x,
        'UP': pygame.K_UP,
        'DOWN': pygame.K_DOWN,
        'LEFT': pygame.K_LEFT,
        'RIGHT': pygame.K_RIGHT,
        'LB': pygame.K_a,
        'RB': pygame.K_s,
        'MENU': pygame.K_ESCAPE,
    }

    @classmethod
    def update_all_buttons(cls):
        """Update all button states - call this once per frame"""
        keys = pygame.key.get_pressed()

        for button_id, state in cls.button_states.items():
            # Update previous state
            state.previous = state.current

            # Check if key is pressed
            key = cls.key_mapping.get(button_id)
            if key:
                state.current = keys[key]
            else:
                state.current = False

            # Check for just pressed
            state.just_pressed = state.current and not state.previous

    def __init__(self, button_id):
        """
        Initialize button

        Args:
            button_id: String identifier for the button ('A', 'B', 'UP', etc.)
        """
        # For pygame keys, button_id will be an integer, convert to string
        if isinstance(button_id, str):
            self.button_id = button_id
        else:
            # Map from thumby hardware constants to our strings
            id_map = {
                0: 'UP',
                1: 'DOWN',
                2: 'LEFT',
                3: 'RIGHT',
                4: 'A',
                5: 'B',
            }
            self.button_id = id_map.get(button_id, 'A')

        # Create button state if it doesn't exist
        if self.button_id not in ButtonClass.button_states:
            ButtonClass.button_states[self.button_id] = ButtonState()

    def pressed(self):
        """Check if button is currently pressed"""
        ButtonClass.update_all_buttons()
        state = ButtonClass.button_states.get(self.button_id)
        return state.current if state else False

    def justPressed(self):
        """Check if button was just pressed this frame"""
        ButtonClass.update_all_buttons()
        state = ButtonClass.button_states.get(self.button_id)
        return state.just_pressed if state else False

    def setPressed(self, value):
        """Manually set button state (for testing)"""
        state = ButtonClass.button_states.get(self.button_id)
        if state:
            state.current = value
