# cutscene_utils.py - 8-bit delta compressed cutscenes with audio for ThumbyColor only
import struct
from os import stat
from gc import collect
from framebuf import FrameBuffer, GS8, RGB565

# These will be injected by platform_loader
display = None
PC = None
audio_load = None
audio_play = None
audio_stop = None
buttonMENU = None

def init_cutscene_utils(display_ref, pc_ref, audio_load_ref, audio_play_ref, audio_stop_ref, button_menu_ref):
    """Initialize references - called by platform_loader"""
    global display, PC, audio_load, audio_play, audio_stop, buttonMENU
    display = display_ref
    PC = pc_ref
    audio_load = audio_load_ref
    audio_play = audio_play_ref
    audio_stop = audio_stop_ref
    buttonMENU = button_menu_ref

def create_cancel_callback():
    """Create a callback that checks for MENU button to cancel cutscene"""
    frame_counter = [0]
    last_check = [False]
    
    def cancel_cutscene_callback(frame_idx):
        frame_counter[0] += 1
        if frame_counter[0] % 6 == 0:
            if buttonMENU and buttonMENU.pressed():
                last_check[0] = True
                return False
        elif last_check[0]:
            return False
        return True
    
    return cancel_cutscene_callback

def play_cutscene_animation(filename, fps=20, frame_callback=None):
    """Play 8-bit delta compressed cutscene with synchronized audio support."""

    if display is None:
        print("Error: cutscene_utils not initialized")
        return

    display.setFPS(fps)

    # Check for corresponding audio file
    audio_playing = False

    if audio_load:
        # Convert filename to .ima audio
        base_name = filename.rsplit('.', 2)[0]  # Remove .COL.bin
        audio_filename = base_name + '.ima'
        try:
            # Check if audio file exists
            stat(audio_filename)
            print(f"Found audio file: {audio_filename}")

            # PC WRAPPER: Calculate required audio playback rate based on video duration
            # Read video header to get frame count
            try:
                with open(filename, 'rb') as vf:
                    magic = vf.read(4)
                    if magic == b'TDL8':
                        width, height, frame_count = struct.unpack('<HHH', vf.read(6))
                        expected_video_duration = frame_count / fps

                        # Read audio header to get sample count
                        with open(audio_filename, 'rb') as af:
                            audio_magic = af.read(4)
                            if audio_magic == b'IMAA':
                                audio_sample_rate = struct.unpack('<I', af.read(4))[0]
                                audio_sample_count = struct.unpack('<I', af.read(4))[0]

                                # Calculate required audio rate for perfect sync
                                required_audio_rate = audio_sample_count / expected_video_duration

                                print(f"[Cutscene Sync] Video: {frame_count} frames @ {fps} FPS = {expected_video_duration:.3f}s")
                                print(f"[Cutscene Sync] Audio: {audio_sample_count} samples, original rate {audio_sample_rate} Hz")
                                print(f"[Cutscene Sync] Required audio rate for sync: {required_audio_rate:.0f} Hz")

                                # Set target duration in audio module for dynamic resampling
                                import sys
                                if 'audio' in sys.modules:
                                    sys.modules['audio'].set_target_duration(expected_video_duration)
            except Exception as sync_err:
                print(f"[Cutscene Sync] Could not calculate sync (will use default): {sync_err}")

            audio_load(audio_filename)
            audio_play()
            audio_playing = True
            print(f"Started audio playback")
        except Exception as e:
            print(f"No audio or failed to play: {e}")
    
    try:
        # Play 8-bit delta compressed cutscene
        _play_8bit_delta_cutscene(filename, frame_callback, fps)
    finally:
        # Stop audio when cutscene ends
        if audio_playing:
            try:
                audio_stop()
                print("Stopped audio playback")
            except:
                pass

def _play_8bit_delta_cutscene(filename, frame_callback, fps):
    """Play 8-bit palette delta-compressed cutscene"""
    
    with open(filename, 'rb') as f:
        # Check magic header for 8-bit delta format
        magic = f.read(4)
        if magic != b'TDL8':
            print(f"Error: {filename} is not 8-bit delta format (TDL8)")
            return
        
        # Read header
        width, height, frame_count = struct.unpack('<HHH', f.read(6))
        print(f"Playing 8-bit delta cutscene: {width}x{height}, {frame_count} frames")
        
        x = (PC.WIDTH - width) // 2
        y = (PC.HEIGHT - height) // 2
        
        # Read palette (256 RGB565 colors)
        palette_data = bytearray(256 * 2)
        f.readinto(palette_data)
        palette = FrameBuffer(palette_data, 256, 1, RGB565)
        
        # Read frame offset table
        frame_offsets = []
        for _ in range(frame_count):
            offset = struct.unpack('<I', f.read(4))[0]
            frame_offsets.append(offset)
        
        # Create persistent 8-bit index buffer
        index_buffer = bytearray(width * height)
        persistent_fb = FrameBuffer(index_buffer, width, height, GS8)
        
        # Create temporary buffer for streaming
        temp_buffer = bytearray(4096)  # 4KB chunk buffer
        
        # Play each frame
        for frame_idx in range(frame_count):
            # Seek to frame data
            f.seek(frame_offsets[frame_idx])
            
            # Read frame type and data
            frame_type = f.read(4)
            data_size = struct.unpack('<I', f.read(4))[0]
            
            # Process frame based on type
            if frame_type == b'FULL':
                # RLE compressed full frame
                _rle_decompress_8bit_stream(f, data_size, index_buffer, temp_buffer)
            elif frame_type == b'URAW':
                # Uncompressed full frame
                _stream_into_buffer(f, data_size, index_buffer, temp_buffer)
            elif frame_type == b'DLTA':
                # Delta frame
                frame_data = f.read(data_size)
                _apply_8bit_delta(index_buffer, frame_data, width, height)
                del frame_data
            elif frame_type == b'SAME':
                # No changes
                pass
            else:
                continue
            
            # Clear display and blit with palette mapping
            display.fill(0)
            display.internal_fb.blit(persistent_fb, x, y, 0, palette)
            
            # Handle frame callback
            if frame_callback:
                if not frame_callback(frame_idx):
                    break
            
            display.update()
            collect()
        
        # Clean up
        del temp_buffer, index_buffer, persistent_fb
        collect()

def _stream_into_buffer(file_handle, data_size, target_buffer, temp_buffer):
    """Stream data directly into buffer"""
    bytes_read = 0
    chunk_size = len(temp_buffer)
    
    while bytes_read < data_size:
        to_read = min(chunk_size, data_size - bytes_read, len(target_buffer) - bytes_read)
        if to_read <= 0:
            break
        
        actual_read = file_handle.readinto(memoryview(temp_buffer)[0:to_read])
        
        for i in range(actual_read):
            if bytes_read + i < len(target_buffer):
                target_buffer[bytes_read + i] = temp_buffer[i]
        
        bytes_read += actual_read

def _rle_decompress_8bit_stream(file_handle, data_size, index_buffer, temp_buffer):
    """Stream RLE decompression for 8-bit data"""
    for i in range(len(index_buffer)):
        index_buffer[i] = 0
    
    buf_pos = 0
    bytes_read = 0
    chunk_size = len(temp_buffer)
    remainder = bytearray()
    
    while bytes_read < data_size and buf_pos < len(index_buffer):
        to_read = min(chunk_size, data_size - bytes_read)
        actual_read = file_handle.readinto(memoryview(temp_buffer)[0:to_read])
        bytes_read += actual_read
        
        if remainder:
            process_data = remainder + temp_buffer[0:actual_read]
        else:
            process_data = memoryview(temp_buffer)[0:actual_read]
        
        remainder = bytearray()
        
        i = 0
        while i + 1 < len(process_data) and buf_pos < len(index_buffer):
            index = process_data[i]
            count = process_data[i + 1] + 1
            
            for _ in range(count):
                if buf_pos < len(index_buffer):
                    index_buffer[buf_pos] = index
                    buf_pos += 1
                else:
                    break
            i += 2
        
        if i < len(process_data):
            remainder = bytearray(process_data[i:])

def _apply_8bit_delta(index_buffer, delta_data, width, height):
    """Apply delta changes to 8-bit index buffer"""
    offset = 0
    if len(delta_data) < 4:
        return
    
    change_count = struct.unpack('<I', delta_data[offset:offset+4])[0]
    offset += 4
    
    for i in range(change_count):
        if offset + 5 <= len(delta_data):
            pixel_idx = struct.unpack('<I', delta_data[offset:offset+4])[0]
            new_index = delta_data[offset+4]
            offset += 5
            
            if pixel_idx < len(index_buffer):
                index_buffer[pixel_idx] = new_index
        else:
            break