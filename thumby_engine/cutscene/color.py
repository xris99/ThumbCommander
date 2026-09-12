# TDL8 (8-bit palette-delta) cutscene player with IMA-ADPCM audio, for
# ThumbyColor and its PC emulation.
import struct
from os import stat
from gc import collect
from array import array
from framebuf import FrameBuffer, GS8, RGB565

# These references are injected by the platform module (init_cutscene_utils)
display = None
PC = None
audio_load = None
audio_play = None
audio_stop = None
buttonCANCEL = None

def init_cutscene_utils(display_ref, pc_ref, audio_load_ref, audio_play_ref, audio_stop_ref, button_cancel_ref):
    """Initialize references - called by the platform module"""
    global display, PC, audio_load, audio_play, audio_stop, buttonCANCEL
    display = display_ref
    PC = pc_ref
    audio_load = audio_load_ref
    audio_play = audio_play_ref
    audio_stop = audio_stop_ref
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
            audio_load(audio_filename)
            audio_play()
            audio_playing = True
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
        
        x = (PC.WIDTH - width) // 2
        y = (PC.HEIGHT - height) // 2
        
        # Create temporary buffer for streaming (used throughout)
        temp_buffer = bytearray(4096)

        # Read palette (256 RGB565 colors)
        palette_data = bytearray(256 * 2)
        f.readinto(palette_data)
        palette = FrameBuffer(palette_data, 256, 1, RGB565)

        # Read frame offset table (pre-allocated array, no dynamic list)
        frame_offsets = array('I', [0] * frame_count)
        for i in range(frame_count):
            f.readinto(memoryview(temp_buffer)[0:4])
            frame_offsets[i] = struct.unpack('<I', temp_buffer[0:4])[0]

        # Create persistent 8-bit index buffer
        index_buffer = bytearray(width * height)
        persistent_fb = FrameBuffer(index_buffer, width, height, GS8)
        header_buffer = bytearray(8)
        header_mv = memoryview(header_buffer)
        run_buffer = bytearray(256)
        run_fb = FrameBuffer(run_buffer, 256, 1, GS8)
        
        # Play each frame
        for frame_idx in range(frame_count):
            # Seek to frame data
            f.seek(frame_offsets[frame_idx])
            
            # Read 8-byte frame header (type byte + data size), allocation-free
            f.readinto(header_mv)
            frame_type = header_buffer[0]
            data_size = header_buffer[4] | (header_buffer[5] << 8) | (header_buffer[6] << 16) | (header_buffer[7] << 24)

            # Process frame based on type (first byte unique: F/U/D/S)
            if frame_type == 0x46:  # b'FULL'
                # RLE compressed full frame
                persistent_fb.fill(0)
                _rle_decompress_8bit_stream(f, data_size, index_buffer, temp_buffer, run_buffer, run_fb)
            elif frame_type == 0x55:  # b'URAW'
                # Uncompressed full frame
                _stream_into_buffer(f, data_size, index_buffer)
            elif frame_type == 0x44:  # b'DLTA'
                # Delta frame - stream using temp_buffer (no allocation)
                _apply_8bit_delta_stream(f, data_size, index_buffer, temp_buffer)
            elif frame_type == 0x53:  # b'SAME'
                # No changes
                pass
            else:
                continue
            
            # Clear display and blit with palette mapping
            display.fill(0)
            display.blit_framebuffer(persistent_fb, x, y, 0, palette)
            
            display.update()
            
            # Handle frame callback
            if frame_callback:
                if not frame_callback(frame_idx):
                    break
        
        # Clean up
        del temp_buffer, index_buffer, persistent_fb, header_buffer, header_mv, run_buffer, run_fb
        collect()

def _stream_into_buffer(file_handle, data_size, target_buffer):
    """Stream data directly into buffer"""
    file_handle.readinto(memoryview(target_buffer)[:min(data_size, len(target_buffer))])

def _rle_decompress_8bit_stream(file_handle, data_size, index_buffer, temp_buffer, run_buffer, run_fb):
    """Stream RLE decompression for 8-bit data - no dynamic allocation"""
    buf_pos = 0
    bytes_remaining = data_size
    chunk_size = (len(temp_buffer) // 2) * 2  # Multiple of 2 bytes per record
    remainder_bytes = 0

    while bytes_remaining > 0 and buf_pos < len(index_buffer):
        to_read = min(chunk_size - remainder_bytes, bytes_remaining)
        actual_read = file_handle.readinto(memoryview(temp_buffer)[remainder_bytes:remainder_bytes + to_read])
        bytes_remaining -= actual_read
        total_bytes = remainder_bytes + actual_read

        # Process complete 2-byte records (index + count)
        i = 0
        while i + 1 < total_bytes and buf_pos < len(index_buffer):
            index = temp_buffer[i]
            count = temp_buffer[i + 1] + 1
            if count >= 8:
                # Long run: fill scratch once, copy in bulk
                run_fb.fill(index)
                end = buf_pos + count
                if end > len(index_buffer):
                    end = len(index_buffer)
                index_buffer[buf_pos:end] = run_buffer[:end - buf_pos]
                buf_pos = end
            else:
                for _ in range(count):
                    if buf_pos < len(index_buffer):
                        index_buffer[buf_pos] = index
                        buf_pos += 1
                    else:
                        break
            i += 2

        # Move remainder to start of buffer
        remainder_bytes = total_bytes - i
        if remainder_bytes > 0:
            temp_buffer[0] = temp_buffer[i]

def _apply_8bit_delta_stream(file_handle, data_size, index_buffer, temp_buffer):
    """Apply delta changes by streaming - no large allocation"""
    # Read change count (4 bytes)
    file_handle.readinto(memoryview(temp_buffer)[0:4])
    change_count = temp_buffer[0] | (temp_buffer[1] << 8) | (temp_buffer[2] << 16) | (temp_buffer[3] << 24)

    bytes_remaining = data_size - 4
    chunk_size = (len(temp_buffer) // 5) * 5  # Multiple of 5 bytes per record
    remainder_bytes = 0
    changes_processed = 0

    while bytes_remaining > 0 and changes_processed < change_count:
        to_read = min(chunk_size - remainder_bytes, bytes_remaining)
        actual_read = file_handle.readinto(memoryview(temp_buffer)[remainder_bytes:remainder_bytes + to_read])
        bytes_remaining -= actual_read
        total_bytes = remainder_bytes + actual_read

        # Process complete 5-byte records (4 byte pixel_idx + 1 byte new_index)
        i = 0
        while i + 5 <= total_bytes and changes_processed < change_count:
            pixel_idx = temp_buffer[i] | (temp_buffer[i + 1] << 8) | (temp_buffer[i + 2] << 16) | (temp_buffer[i + 3] << 24)
            if pixel_idx < len(index_buffer):
                index_buffer[pixel_idx] = temp_buffer[i+4]
            i += 5
            changes_processed += 1

        # Move remainder to start of buffer
        remainder_bytes = total_bytes - i
        if remainder_bytes > 0:
            for j in range(remainder_bytes):
                temp_buffer[j] = temp_buffer[i + j]