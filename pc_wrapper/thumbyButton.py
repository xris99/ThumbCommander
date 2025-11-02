"""
Thumby button emulation for PC
Maps keyboard keys to button states
Button state is updated once per frame by engine.tick()
"""

# Lazy import pygame
pygame = None

# Module-level button state - updated once per frame by engine.tick()
_current_keys = {}
_previous_keys = {}
_initialized = False

# Keyboard mapping
_key_mapping = {
    'A': None,
    'B': None,
    'UP': None,
    'DOWN': None,
    'LEFT': None,
    'RIGHT': None,
    'LB': None,
    'RB': None,
    'MENU': None,
}


def _ensure_pygame():
    """Ensure pygame is imported"""
    global pygame
    if pygame is None:
        try:
            import pygame as pg
            pygame = pg
        except ImportError:
            pass


def _init_key_mapping():
    """Initialize key mapping once pygame is available"""
    global _initialized
    if _initialized:
        return

    _ensure_pygame()
    if pygame:
        _key_mapping['A'] = pygame.K_y  # Y key for German keyboard layout
        _key_mapping['B'] = pygame.K_x
        _key_mapping['UP'] = pygame.K_UP
        _key_mapping['DOWN'] = pygame.K_DOWN
        _key_mapping['LEFT'] = pygame.K_LEFT
        _key_mapping['RIGHT'] = pygame.K_RIGHT
        _key_mapping['LB'] = pygame.K_a
        _key_mapping['RB'] = pygame.K_s
        _key_mapping['MENU'] = pygame.K_ESCAPE
        _initialized = True


def update_button_state():
    """
    Update button states - called ONCE per frame by engine.tick()
    Reads pygame key state and stores in module-level variables
    """
    global _current_keys, _previous_keys

    _ensure_pygame()
    if pygame is None:
        return

    _init_key_mapping()

    # Store previous state
    _previous_keys = _current_keys.copy()

    # Read current pygame key state
    keys = pygame.key.get_pressed()

    # Update current state for all mapped buttons
    _current_keys = {}
    for button_id, key_code in _key_mapping.items():
        if key_code is not None:
            _current_keys[button_id] = keys[key_code]
        else:
            _current_keys[button_id] = False


def _is_key_pressed(button_id):
    """Check if a button is currently pressed"""
    return _current_keys.get(button_id, False)


def _was_key_pressed(button_id):
    """Check if a button was pressed in the previous frame"""
    return _previous_keys.get(button_id, False)


class ButtonClass:
    """
    Button class compatible with Thumby button API
    Queries module-level state updated by engine.tick()
    """

    def __init__(self, button_id):
        """
        Initialize button

        Args:
            button_id: String identifier or integer constant
        """
        # Map from thumby hardware constants to our strings
        if isinstance(button_id, str):
            self.button_id = button_id
        else:
            id_map = {
                0: 'UP',
                1: 'DOWN',
                2: 'LEFT',
                3: 'RIGHT',
                4: 'A',
                5: 'B',
            }
            self.button_id = id_map.get(button_id, 'A')

    def pressed(self):
        """Check if button is currently pressed"""
        return _is_key_pressed(self.button_id)

    def justPressed(self):
        """
        Check if button was just pressed this frame
        Clears the stored state after reading to prevent double input
        """
        global _current_keys, _previous_keys
        current = _is_key_pressed(self.button_id)
        previous = _was_key_pressed(self.button_id)
        just_pressed = current and not previous

        # Clear stored state to prevent double reading of the same press
        if just_pressed:
            _current_keys[self.button_id] = False
            _previous_keys[self.button_id] = False

        return just_pressed

    def setPressed(self, value):
        """Manually set button state (for testing)"""
        global _current_keys
        _current_keys[self.button_id] = value
