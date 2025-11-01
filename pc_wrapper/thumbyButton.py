"""
Thumby button emulation for PC
Maps keyboard keys to button states
"""

# Lazy import pygame - only when actually needed
pygame = None


def _ensure_pygame():
    """Ensure pygame is imported"""
    global pygame
    if pygame is None:
        try:
            import pygame as pg
            pygame = pg
        except ImportError:
            pass  # pygame not available


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
        'A': None,  # Will be set to pygame.K_z when pygame is loaded
        'B': None,
        'UP': None,
        'DOWN': None,
        'LEFT': None,
        'RIGHT': None,
        'LB': None,
        'RB': None,
        'MENU': None,
    }

    @classmethod
    def _init_key_mapping(cls):
        """Initialize key mapping once pygame is available"""
        _ensure_pygame()
        if pygame and cls.key_mapping['A'] is None:
            cls.key_mapping['A'] = pygame.K_z
            cls.key_mapping['B'] = pygame.K_x
            cls.key_mapping['UP'] = pygame.K_UP
            cls.key_mapping['DOWN'] = pygame.K_DOWN
            cls.key_mapping['LEFT'] = pygame.K_LEFT
            cls.key_mapping['RIGHT'] = pygame.K_RIGHT
            cls.key_mapping['LB'] = pygame.K_a
            cls.key_mapping['RB'] = pygame.K_s
            cls.key_mapping['MENU'] = pygame.K_ESCAPE

    @classmethod
    def update_all_buttons(cls):
        """Update all button states - call this once per frame"""
        _ensure_pygame()
        if pygame is None:
            return

        cls._init_key_mapping()
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
