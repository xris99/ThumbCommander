# Grayscale (1-bit 4-level) cutscene player for the original Thumby.
# The Thumby has no audio, so cutscenes are silent sprite animations.
#
# Like the color cutscene player, this module is initialized by dependency
# injection from the platform module (init_grayscale_cutscene) so the engine
# never imports the platform module (no circular imports, no unused modules
# loaded into the limited Thumby RAM).
from os import stat
from gc import collect

# Injected by the platform module
display = None
PC = None
buttonCANCEL = None


def init_grayscale_cutscene(display_ref, pc_ref, button_cancel_ref):
    """Initialize references - called by the platform module."""
    global display, PC, buttonCANCEL
    display = display_ref
    PC = pc_ref
    buttonCANCEL = button_cancel_ref


class CancelCallback:
    __slots__ = ('counter',)

    def __init__(self):
        self.counter = 0

    def __call__(self, _):
        self.counter += 1
        if self.counter >= 6:
            self.counter = 0
            if buttonCANCEL and buttonCANCEL.justPressed():
                return False
        return True


def create_cancel_callback():
    return CancelCallback()


def play_cutscene_animation(filename, fps=20, frame_callback=None):
    """Play a grayscale sprite animation (BIT + SHD files, no audio)."""
    if display is None:
        print("Error: grayscale cutscene not initialized")
        return

    display.setFPS(fps)

    # The SHD (shading) file is required for 4-level dither output
    shd_filename = filename.replace('.BIT.bin', '.SHD.bin')

    try:
        # Parse dimensions from the filename: <name>_<width>_<height>.BIT.bin
        parts = filename.split('_')
        if len(parts) >= 3:
            try:
                width = int(parts[-2])
                height = int(parts[-1].replace('.BIT.bin', ''))
            except ValueError:
                # Default dimensions if parsing fails
                width, height = 74, 30
        else:
            width, height = 74, 30

        # Center the animation
        x = (PC.WIDTH - width) // 2
        y = (PC.HEIGHT - height) // 2

        # Buffer size for one frame of the 1-bit bitmap
        bitmap_byte_count = width * ((height + 7) // 8)

        with open(filename, 'rb') as bit_file, open(shd_filename, 'rb') as shd_file:
            # Frame count from file size
            file_size = stat(filename)[6]
            frame_count = file_size // bitmap_byte_count

            print(f"Playing grayscale cutscene: {width}x{height}, {frame_count} frames")

            # Reusable frame buffers (no per-frame allocation)
            bit_buffer = bytearray(bitmap_byte_count)
            shd_buffer = bytearray(bitmap_byte_count)

            for frame_idx in range(frame_count):
                display.fill(0)

                bit_file.readinto(bit_buffer)
                shd_file.readinto(shd_buffer)

                # Native 4-level dither blit
                display.blit((bit_buffer, shd_buffer), x, y, width, height, -1, 0, 0)
                display.update()

                if frame_callback:
                    if not frame_callback(frame_idx):
                        break

            del bit_buffer, shd_buffer
            collect()

    except Exception as e:
        print(f"Error playing grayscale cutscene\n{filename}:\n{e}")
