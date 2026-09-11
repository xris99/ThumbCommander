"""
PC-Specific Audio Implementation for ThumbCommander
Uses pygame.mixer for playback - bypasses all GIL/threading issues
Provides same API as hardware audio.py
"""

import struct
import array
import threading
import os

# Lazy import pygame
pygame = None
_pygame_initialized = False

def _ensure_pygame():
    """Ensure pygame and pygame.mixer are imported and initialized"""
    global pygame, _pygame_initialized
    if pygame is None:
        try:
            import pygame as pg
            pygame = pg
        except ImportError:
            return False

    # Ensure mixer is initialized
    if not _pygame_initialized:
        try:
            mixer_init = pygame.mixer.get_init()
            if not mixer_init:
                # Initialize pygame.mixer at 15625 Hz (hardware sample rate)
                pygame.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
                try:
                    pygame.mixer.init()
                    print(f"[Audio PC] Initialized pygame.mixer at 15625 Hz")
                except pygame.error as e:
                    # If real audio fails, try dummy driver (for headless environments)
                    print(f"[Audio PC] Real audio failed: {e}")
                    print(f"[Audio PC] Trying dummy audio driver for testing...")
                    os.environ['SDL_AUDIODRIVER'] = 'dummy'
                    pygame.mixer.quit()
                    pygame.mixer.init()
                    print(f"[Audio PC] Initialized pygame.mixer with dummy driver")
            else:
                print(f"[Audio PC] pygame.mixer already initialized at {mixer_init[0]} Hz")
            _pygame_initialized = True
            return True
        except Exception as e:
            print(f"[Audio PC] Failed to initialize pygame.mixer: {e}")
            return False
    return True


def _resample_audio(samples, source_rate, target_rate):
    """
    Resample audio from source_rate to target_rate using linear interpolation

    Args:
        samples: array of 16-bit PCM samples
        source_rate: original sample rate (e.g., 8000 Hz)
        target_rate: target sample rate (e.g., 15625 Hz)

    Returns:
        array of resampled 16-bit PCM samples
    """
    if source_rate == target_rate:
        return samples

    # Calculate resampling ratio
    ratio = target_rate / source_rate
    new_length = int(len(samples) * ratio)

    # Create output array
    resampled = array.array('h', [0] * new_length)

    # Linear interpolation
    for i in range(new_length):
        # Calculate position in source array
        src_pos = i / ratio
        src_idx = int(src_pos)

        # Bounds check
        if src_idx >= len(samples) - 1:
            resampled[i] = samples[-1]
        else:
            # Linear interpolation between two samples
            frac = src_pos - src_idx
            sample1 = samples[src_idx]
            sample2 = samples[src_idx + 1]
            resampled[i] = int(sample1 + (sample2 - sample1) * frac)

    return resampled


class IMA_ADPCM_Decoder:
    """IMA ADPCM decoder - same algorithm as hardware"""

    # IMA ADPCM tables
    INDEX_TABLE = array.array('i', [
        -1, -1, -1, -1, 2, 4, 6, 8,
        -1, -1, -1, -1, 2, 4, 6, 8
    ])

    STEP_TABLE = array.array('h', [
        7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
        19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
        50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
        130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
        337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
        876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
        2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
        5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
        15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
    ])

    def __init__(self):
        self.prediction = 32768
        self.index = 0
        self.step = self.STEP_TABLE[0]

    def reset(self):
        """Reset decoder state"""
        self.prediction = 32768
        self.index = 0
        self.step = self.STEP_TABLE[0]

    def decode_nibble(self, nibble):
        """Decode single 4-bit nibble to 16-bit PCM sample"""
        # Calculate difference
        diff = self.step >> 3
        if nibble & 0b100:
            diff += self.step
        if nibble & 0b10:
            diff += (self.step >> 1)
        if nibble & 0b1:
            diff += (self.step >> 2)

        # Apply difference
        if nibble & 0b1000:
            self.prediction -= diff
            if self.prediction < 0:
                self.prediction = 0
        else:
            self.prediction += diff
            if self.prediction > 65535:
                self.prediction = 65535

        # Update index and step
        self.index += self.INDEX_TABLE[nibble]
        if self.index < 0:
            self.index = 0
        elif self.index > 88:
            self.index = 88
        self.step = self.STEP_TABLE[self.index]

        return self.prediction

    def decode_data(self, ima_data):
        """Decode IMA ADPCM data to unsigned 16-bit PCM samples"""
        samples = []
        for byte in ima_data:
            # High nibble first (even sample)
            high_nibble = (byte >> 4) & 0x0F
            samples.append(self.decode_nibble(high_nibble))

            # Low nibble second (odd sample)
            low_nibble = byte & 0x0F
            samples.append(self.decode_nibble(low_nibble))

        return samples


class AudioState:
    """Global audio state - singleton"""
    def __init__(self):
        self.current_sound = None
        self.current_channel = None
        self.sample_rate = 15625
        self.volume = 100
        self.loop_enabled = False
        self.loop_start = 0
        self.loop_end = 0
        self.end_callback = None
        self.callback_args = None
        self.file_handles = []  # For open_id/play_id
        self.playing = False
        self.lock = threading.Lock()
        self.callback_timer = None

        # Ensure pygame mixer is initialized
        if _ensure_pygame():
            mixer_init = pygame.mixer.get_init()
            if mixer_init:
                self.sample_rate = mixer_init[0]
                print(f"[Audio PC] Using pygame.mixer at {self.sample_rate} Hz")


# Global audio state
audio = AudioState()


def load(ima_filename):
    """Load and play IMA ADPCM file"""
    if not _ensure_pygame():
        return False

    try:
        with open(ima_filename, "rb") as f:
            # Read IMA header
            magic = f.read(4)
            if magic != b'IMAA':
                print(f"[Audio PC] Invalid IMA file: {ima_filename}")
                return False

            sample_rate = struct.unpack('<I', f.read(4))[0]
            sample_count = struct.unpack('<I', f.read(4))[0]
            f.read(12)  # Skip reserved bytes

            # Read and decode IMA ADPCM data
            ima_data = f.read()

        print(f"[Audio PC] Loading {ima_filename}: {sample_count} samples @ {sample_rate} Hz")

        # Decode to PCM
        decoder = IMA_ADPCM_Decoder()
        pcm_samples = decoder.decode_data(ima_data)

        # Convert to signed 16-bit array
        signed_samples = array.array('h')
        for sample in pcm_samples[:sample_count]:  # Only use declared sample count
            signed = int(sample) - 32768
            signed = max(-32768, min(32767, signed))
            signed_samples.append(signed)

        # Resample to match pygame.mixer frequency if needed
        mixer_freq = 15625  # pygame.mixer is always initialized at 15625 Hz
        if sample_rate != mixer_freq:
            print(f"[Audio PC] Resampling from {sample_rate} Hz to {mixer_freq} Hz")
            signed_samples = _resample_audio(signed_samples, sample_rate, mixer_freq)
            # Update sample_count for resampled audio
            sample_count = len(signed_samples)

        # Apply volume
        if audio.volume != 100:
            signed_samples = array.array('h', [int(s * audio.volume / 100) for s in signed_samples])

        # Create pygame Sound
        audio_bytes = struct.pack('<' + 'h' * len(signed_samples), *signed_samples)

        with audio.lock:
            audio.current_sound = pygame.mixer.Sound(buffer=audio_bytes)
            audio.loop_enabled = False
            audio.loop_start = 0
            audio.loop_end = sample_count

            # Get or create channel
            if audio.current_channel is None:
                audio.current_channel = pygame.mixer.Channel(0)

            # Play the sound
            loops = -1 if audio.loop_enabled else 0
            audio.current_channel.play(audio.current_sound, loops=loops)
            audio.playing = True

            # Set up end callback if not looping
            if not audio.loop_enabled and audio.end_callback:
                _schedule_end_callback(len(signed_samples) / sample_rate)

        return True

    except Exception as e:
        print(f"[Audio PC] Error loading {ima_filename}: {e}")
        import traceback
        traceback.print_exc()
        return False


def play():
    """Resume playback if paused"""
    with audio.lock:
        if audio.current_channel and audio.current_sound:
            if not audio.current_channel.get_busy():
                loops = -1 if audio.loop_enabled else 0
                audio.current_channel.play(audio.current_sound, loops=loops)
                audio.playing = True
                return True
    return False


def stop():
    """Stop playback"""
    with audio.lock:
        if audio.current_channel:
            audio.current_channel.stop()
        audio.playing = False

        # Cancel callback timer
        if audio.callback_timer:
            try:
                audio.callback_timer.cancel()
            except:
                pass
            audio.callback_timer = None


def set_volume(volume):
    """Set volume 0-200 (100 = normal)"""
    audio.volume = max(0, min(200, int(volume)))
    with audio.lock:
        if audio.current_sound:
            # pygame volume is 0.0 to 1.0
            audio.current_sound.set_volume(audio.volume / 100.0)


def get_volume():
    """Get current volume"""
    return audio.volume


def set_loop(enabled=True, start_sample=0, end_sample=0):
    """Set loop points"""
    audio.loop_enabled = enabled
    audio.loop_start = start_sample & ~1  # Even samples only
    audio.loop_end = end_sample & ~1 if end_sample else 0

    # Note: pygame doesn't support loop points, only full loop
    # So we just enable/disable looping
    with audio.lock:
        if audio.current_channel and audio.current_sound and audio.playing:
            # Restart with new loop setting
            loops = -1 if enabled else 0
            audio.current_channel.play(audio.current_sound, loops=loops)


def set_loop_seconds(enabled=True, start_seconds=0.0, end_seconds=0.0):
    """Set loop points in seconds"""
    start_sample = int(start_seconds * audio.sample_rate)
    end_sample = int(end_seconds * audio.sample_rate) if end_seconds > 0 else 0
    set_loop(enabled, start_sample, end_sample)


def get_loop_status():
    """Get current loop settings"""
    return {
        'enabled': audio.loop_enabled,
        'start_sample': audio.loop_start,
        'end_sample': audio.loop_end,
        'start_seconds': audio.loop_start / audio.sample_rate if audio.sample_rate > 0 else 0,
        'end_seconds': audio.loop_end / audio.sample_rate if audio.sample_rate > 0 else 0
    }


def set_end_callback(callback_func, *args):
    """Set playback end callback"""
    audio.end_callback = callback_func
    audio.callback_args = args if args else None


def clear_end_callback():
    """Clear callback"""
    audio.end_callback = None
    audio.callback_args = None


def _schedule_end_callback(duration_seconds):
    """Schedule callback to fire when playback ends"""
    if not audio.end_callback:
        return

    def fire_callback():
        if audio.end_callback:
            try:
                if audio.callback_args:
                    audio.end_callback(*audio.callback_args)
                else:
                    audio.end_callback()
            except Exception as e:
                print(f"[Audio PC] Callback error: {e}")

    # Schedule callback using threading.Timer
    audio.callback_timer = threading.Timer(duration_seconds, fire_callback)
    audio.callback_timer.daemon = True
    audio.callback_timer.start()


def is_playing():
    """Check if playing"""
    with audio.lock:
        if audio.current_channel:
            return audio.current_channel.get_busy()
    return False


def get_position():
    """Get position 0-1"""
    # pygame doesn't provide position info easily
    return 0.0


def get_position_seconds():
    """Get position in seconds"""
    return 0.0


def get_duration_seconds():
    """Get duration in seconds"""
    with audio.lock:
        if audio.current_sound:
            return audio.current_sound.get_length()
    return 0.0


def get_status():
    """Get current playback status"""
    return {
        'playing': is_playing(),
        'sample_rate': audio.sample_rate,
        'volume': audio.volume,
        'loop_enabled': audio.loop_enabled,
        'callback_set': audio.end_callback is not None,
    }


# === File Handle Management for FXEngine ===

def open_id(ima_filename, file_id=None):
    """Open file for quick switching (pre-decode and store)"""
    if not _ensure_pygame():
        return -1

    try:
        with open(ima_filename, "rb") as f:
            # Read IMA header
            magic = f.read(4)
            if magic != b'IMAA':
                return -1

            sample_rate = struct.unpack('<I', f.read(4))[0]
            sample_count = struct.unpack('<I', f.read(4))[0]
            f.read(12)

            # Read and decode
            ima_data = f.read()

        decoder = IMA_ADPCM_Decoder()
        pcm_samples = decoder.decode_data(ima_data)

        # Convert to signed 16-bit array
        signed_samples = array.array('h')
        for sample in pcm_samples[:sample_count]:
            signed = int(sample) - 32768
            signed = max(-32768, min(32767, signed))
            signed_samples.append(signed)

        # Resample to match pygame.mixer frequency if needed
        mixer_freq = 15625  # pygame.mixer is always initialized at 15625 Hz
        original_sample_rate = sample_rate
        if sample_rate != mixer_freq:
            print(f"[Audio PC] Resampling {ima_filename}: {sample_rate} Hz -> {mixer_freq} Hz")
            signed_samples = _resample_audio(signed_samples, sample_rate, mixer_freq)
            # Update sample_count for resampled audio
            sample_count = len(signed_samples)
            sample_rate = mixer_freq  # Update to match actual playback rate

        # Apply volume
        if audio.volume != 100:
            signed_samples = array.array('h', [int(s * audio.volume / 100) for s in signed_samples])

        # Create pygame Sound
        audio_bytes = struct.pack('<' + 'h' * len(signed_samples), *signed_samples)
        sound = pygame.mixer.Sound(buffer=audio_bytes)

        # Store in file handles (with original sample rate for reference)
        file_info = (sound, original_sample_rate, sample_count)

        if file_id is None:
            audio.file_handles.append(file_info)
            print(f"[Audio PC] Opened {ima_filename} as ID {len(audio.file_handles)-1}")
            return len(audio.file_handles) - 1
        else:
            # Extend list if needed
            while len(audio.file_handles) <= file_id:
                audio.file_handles.append(None)

            audio.file_handles[file_id] = file_info
            print(f"[Audio PC] Opened {ima_filename} as ID {file_id}")
            return file_id

    except Exception as e:
        print(f"[Audio PC] Error opening {ima_filename}: {e}")
        return -1


def play_id(file_id=0):
    """Play pre-opened file"""
    if file_id >= len(audio.file_handles) or not audio.file_handles[file_id]:
        print(f"[Audio PC] Invalid file ID: {file_id}")
        return False

    try:
        sound, sample_rate, sample_count = audio.file_handles[file_id]

        with audio.lock:
            audio.current_sound = sound

            # Get or create channel
            if audio.current_channel is None:
                audio.current_channel = pygame.mixer.Channel(0)

            # Play the sound
            loops = -1 if audio.loop_enabled else 0
            audio.current_channel.play(sound, loops=loops)
            audio.playing = True

            # Schedule end callback if not looping
            if not audio.loop_enabled and audio.end_callback:
                duration = sample_count / sample_rate
                _schedule_end_callback(duration)

        print(f"[Audio PC] Playing file ID {file_id}")
        return True

    except Exception as e:
        print(f"[Audio PC] Error playing file ID {file_id}: {e}")
        return False


def close_ids():
    """Close all file handles"""
    stop()
    audio.file_handles = []
    print(f"[Audio PC] Closed all file handles")


# Print initialization message
print(f"[Audio PC] PC-specific audio module loaded (pygame.mixer backend)")
