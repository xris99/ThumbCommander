"""
Grayscale display stub for PC
This is here for compatibility but won't be used in ThumbyColor mode
"""


class DummyDisplay:
    """Dummy display for grayscale mode"""

    def enableGrayscale(self):
        pass

    def setFPS(self, fps):
        pass

    def fill(self, color):
        pass

    def update(self):
        pass


class DummySprite:
    """Dummy sprite for grayscale mode"""

    def __init__(self, *args, **kwargs):
        pass


display = DummyDisplay()
Sprite = DummySprite


def play_cutscene_animation(filename, frames, cancel_callback=None):
    """Dummy cutscene animation"""
    pass


def create_cancel_callback():
    """Dummy cancel callback"""
    return lambda: False
