#!/usr/bin/env python3
"""
WAV to IMA ADPCM Converter
Converts single channel WAV files to IMA ADPCM format with custom header.

Usage: python wav_to_ima.py input_file.wav
Output: input_file.ima (IMA ADPCM data with 24-byte header)
"""

import sys
import wave
import struct
import os

class IMAEncoder:
    """IMA ADPCM encoder implementation following the official IMA specification"""
    
    # IMA ADPCM step size table (from official IMA spec)
    STEP_TABLE = [
        7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
        34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
        157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544,
        598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878,
        2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894,
        6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818,
        18500, 20350, 22385, 24623, 27086, 29794, 32767
    ]
    
    # Index table for step size adaptation (from official IMA spec)
    INDEX_TABLE = [
        -1, -1, -1, -1, 2, 4, 6, 8,
        -1, -1, -1, -1, 2, 4, 6, 8
    ]
    
    def __init__(self):
        # Initialize predictor state (from IMA spec)
        self.predicted_sample = 0  # Output of ADPCM predictor
        self.index = 0  # Index into step size table
        self.stepsize = 7  # Quantizer step size
    
    def encode_sample(self, original_sample):
        """
        Encode a single 16-bit PCM sample to 4-bit IMA ADPCM
        Following the official IMA specification algorithm
        """
        # Find difference from predicted sample
        difference = original_sample - self.predicted_sample
        
        # Set sign bit and find absolute value of difference
        if difference >= 0:
            new_sample = 0  # Set sign bit (new_sample[3]) to 0
        else:
            new_sample = 8  # Set sign bit (new_sample[3]) to 1
            difference = -difference  # Absolute value of negative difference
        
        # Quantize difference down to four bits using successive approximation
        mask = 4  # Used to set bits in new_sample
        temp_stepsize = self.stepsize  # Store quantizer stepsize for later use
        
        for i in range(3):  # Quantize difference down to four bits
            if difference >= temp_stepsize:
                # new_sample[2:0] = 4 * (difference/stepsize)
                new_sample |= mask  # Perform division through repeated subtraction
                difference -= temp_stepsize
            temp_stepsize >>= 1  # Adjust comparator for next iteration
            mask >>= 1  # Adjust bit-set mask for next iteration
        
        # Update predictor and step size using the same logic as decoder
        self._update_predictor(new_sample)
        
        return new_sample
    
    def _update_predictor(self, new_sample):
        """
        Update predictor and step size using the same algorithm as the decoder
        This ensures encoder/decoder consistency
        """
        # Calculate difference = (new_sample + 0.5) * stepsize/4
        difference = 0
        if new_sample & 4:  # Perform multiplication through repetitive addition
            difference += self.stepsize
        if new_sample & 2:
            difference += self.stepsize >> 1
        if new_sample & 1:
            difference += self.stepsize >> 2
        # (new_sample + 0.5) * stepsize/4 = new_sample * stepsize/4 + stepsize/8
        difference += self.stepsize >> 3
        
        if new_sample & 8:  # Account for sign bit
            difference = -difference
        
        # Adjust predicted sample based on calculated difference
        self.predicted_sample += difference
        
        # Check for overflow (clamp to 16-bit signed range)
        if self.predicted_sample > 32767:
            self.predicted_sample = 32767
        elif self.predicted_sample < -32768:
            self.predicted_sample = -32768
        
        # Compute new stepsize
        # Adjust index into stepsize lookup table using new_sample
        self.index += self.INDEX_TABLE[new_sample]
        
        # Check for index underflow/overflow
        if self.index < 0:
            self.index = 0
        elif self.index > 88:
            self.index = 88
        
        # Find new quantizer stepsize
        self.stepsize = self.STEP_TABLE[self.index]

def read_wav_file(filename):
    """Read WAV file and return sample data and parameters"""
    try:
        with wave.open(filename, 'rb') as wav_file:
            # Check if mono (single channel)
            if wav_file.getnchannels() != 1:
                raise ValueError(f"File must be mono (single channel). Found {wav_file.getnchannels()} channels.")
            
            # Check sample width (should be 16-bit)
            if wav_file.getsampwidth() != 2:
                raise ValueError(f"File must be 16-bit. Found {wav_file.getsampwidth() * 8}-bit.")
            
            # Get file parameters
            sample_rate = wav_file.getframerate()
            num_frames = wav_file.getnframes()
            
            # Read raw audio data
            raw_data = wav_file.readframes(num_frames)
            
            # Convert to list of 16-bit signed integers
            samples = []
            for i in range(0, len(raw_data), 2):
                sample = struct.unpack('<h', raw_data[i:i+2])[0]
                samples.append(sample)
            
            return samples, sample_rate, num_frames
            
    except wave.Error as e:
        raise ValueError(f"Error reading WAV file: {e}")
    except FileNotFoundError:
        raise FileNotFoundError(f"WAV file not found: {filename}")

def write_ima_file(filename, ima_data, sample_rate, num_samples, nibble_order):
    """Write IMA ADPCM data to file with custom header"""
    try:
        with open(filename, 'wb') as ima_file:
            # Write custom header
            # Magic number (4 bytes): "IMAA"
            ima_file.write(b'IMAA')
            
            # Sample rate (4 bytes, little endian)
            ima_file.write(struct.pack('<I', sample_rate))
            
            # Number of original samples (4 bytes, little endian)
            ima_file.write(struct.pack('<I', num_samples))
            
            # Number of compressed bytes (4 bytes, little endian)
            ima_file.write(struct.pack('<I', len(ima_data)))
            
            # Nibble order flag (4 bytes, little endian)
            # 0 = low_first, 1 = high_first
            order_flag = 1 if nibble_order == 'high_first' else 0
            ima_file.write(struct.pack('<I', order_flag))
            
            # Reserved for future use (4 bytes)
            ima_file.write(struct.pack('<I', 0))
            
            # Write compressed data
            ima_file.write(ima_data)
            
    except IOError as e:
        raise IOError(f"Error writing IMA file: {e}")

def read_ima_header(filename, quiet=False):
    """Read and display IMA file header information"""
    try:
        with open(filename, 'rb') as ima_file:
            # Read magic number
            magic = ima_file.read(4)
            if magic != b'IMAA':
                if not quiet:
                    print(f"Warning: Invalid magic number: {magic}")
                return None
            
            # Read header fields
            sample_rate = struct.unpack('<I', ima_file.read(4))[0]
            num_samples = struct.unpack('<I', ima_file.read(4))[0]
            data_size = struct.unpack('<I', ima_file.read(4))[0]
            nibble_order = struct.unpack('<I', ima_file.read(4))[0]
            reserved = struct.unpack('<I', ima_file.read(4))[0]
            
            order_str = 'high_first' if nibble_order == 1 else 'low_first'
            
            if not quiet:
                print(f"IMA file header:")
                print(f"  Magic: {magic.decode('ascii', errors='ignore')}")
                print(f"  Sample rate: {sample_rate} Hz")
                print(f"  Number of samples: {num_samples}")
                print(f"  Compressed data size: {data_size} bytes")
                print(f"  Nibble order: {order_str}")
                print(f"  Reserved: {reserved}")
            
            return {
                'sample_rate': sample_rate,
                'num_samples': num_samples,
                'data_size': data_size,
                'nibble_order': order_str,
                'reserved': reserved
            }
            
    except (IOError, struct.error) as e:
        if not quiet:
            print(f"Error reading IMA header: {e}")
        return None

def convert_wav_to_ima(wav_filename, nibble_order='low_first'):
    """
    Convert WAV file to IMA ADPCM format
    nibble_order: 'low_first' (first sample in low nibble) or 'high_first' (first sample in high nibble)
    """
    # Validate input file
    if not wav_filename.lower().endswith('.wav'):
        raise ValueError("Input file must have .wav extension")
    
    if not os.path.exists(wav_filename):
        raise FileNotFoundError(f"Input file not found: {wav_filename}")
    
    # Generate output filename
    base_name = os.path.splitext(wav_filename)[0]
    ima_filename = base_name + '.ima'
    
    print(f"Converting: {wav_filename} -> {ima_filename}")
    print(f"Nibble order: {nibble_order}")
    
    # Read WAV file
    try:
        samples, sample_rate, num_frames = read_wav_file(wav_filename)
        print(f"Input: {num_frames} samples, {sample_rate} Hz, 16-bit mono")
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return False
    
    # Encode to IMA ADPCM
    encoder = IMAEncoder()
    ima_data = bytearray()
    
    # Process samples in pairs (each byte contains 2 samples)
    for i in range(0, len(samples), 2):
        # Encode first sample
        sample1 = samples[i]
        code1 = encoder.encode_sample(sample1)
        
        # Encode second sample if it exists
        if i + 1 < len(samples):
            sample2 = samples[i + 1]
            code2 = encoder.encode_sample(sample2)
        else:
            code2 = 0  # Pad with silence if odd number of samples
        
        # Combine two 4-bit codes into one byte based on nibble order
        if nibble_order == 'low_first':
            # First sample in low nibble (bits 0-3), second in high nibble (bits 4-7)
            byte_val = (code2 << 4) | code1
        else:  # 'high_first'
            # First sample in high nibble (bits 4-7), second in low nibble (bits 0-3)
            byte_val = (code1 << 4) | code2
        
        ima_data.append(byte_val)
    
    # Write IMA file
    try:
        write_ima_file(ima_filename, ima_data, sample_rate, len(samples), nibble_order)
        
        # Calculate compression ratio
        original_size = len(samples) * 2  # 16-bit samples
        compressed_size = len(ima_data) + 24  # Data + 24-byte header
        compression_ratio = original_size / compressed_size
        
        print(f"Output: {len(ima_data)} bytes + 24-byte header")
        print(f"Compression: {original_size} -> {compressed_size} bytes (ratio: {compression_ratio:.1f}:1)")
        print(f"Successfully created: {ima_filename}")
        
        # Display header info for verification
        print("\nHeader verification:")
        read_ima_header(ima_filename)
        return True
        
    except IOError as e:
        print(f"Error: {e}")
        return False

def main():
    """Main function"""
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python wav_to_ima.py input_file.wav [nibble_order]")
        print("   or: python wav_to_ima.py input_file.ima --info")
        print("Converts single channel WAV files to IMA ADPCM format with custom header")
        print("nibble_order: 'low_first' (default) or 'high_first'")
        print("")
        print("Output format:")
        print("  24-byte header + compressed IMA ADPCM data")
        print("  Header contains: magic, sample_rate, num_samples, data_size, nibble_order, reserved")
        print("")
        print("Options:")
        print("  --info: Display header information for existing IMA file")
        print("")
        print("If the output doesn't play correctly, try the other nibble order:")
        print("  python wav_to_ima.py input_file.wav high_first")
        sys.exit(1)
    
    input_filename = sys.argv[1]
    
    # Check if user wants to read header info
    if len(sys.argv) == 3 and sys.argv[2] == '--info':
        if not input_filename.lower().endswith('.ima'):
            print("Error: --info option requires an .ima file")
            sys.exit(1)
        
        header_info = read_ima_header(input_filename)
        sys.exit(0 if header_info else 1)
    
    # Normal conversion mode
    wav_filename = input_filename
    nibble_order = sys.argv[2] if len(sys.argv) > 2 else 'low_first'
    
    if nibble_order not in ['low_first', 'high_first']:
        print("Error: nibble_order must be 'low_first' or 'high_first'")
        sys.exit(1)
    
    try:
        success = convert_wav_to_ima(wav_filename, nibble_order)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nConversion interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
