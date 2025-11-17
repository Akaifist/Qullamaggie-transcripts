#!/usr/bin/env python3
"""
Convert existing WAV audio files to compressed MP3 format to save space.
"""

import os
import subprocess
from pathlib import Path

def convert_wav_to_mp3(wav_file: str, mp3_file: str) -> bool:
    """Convert WAV file to compressed MP3 using ffmpeg."""
    cmd = [
        'ffmpeg', '-i', wav_file,
        '-acodec', 'libmp3lame',
        '-ab', '32k',  # 32kbps bitrate for speech
        '-ar', '16000',  # 16kHz sample rate
        '-y',  # Overwrite output file
        mp3_file
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {wav_file}: {e.stderr}")
        return False
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg.")
        return False

def main():
    videos_dir = Path("videos")
    
    if not videos_dir.exists():
        print("videos/ directory not found!")
        return
    
    wav_files = list(videos_dir.rglob("*.wav"))
    
    if not wav_files:
        print("No WAV files found to convert.")
        return
    
    print(f"Found {len(wav_files)} WAV file(s) to convert...\n")
    
    total_saved = 0
    for wav_file in wav_files:
        mp3_file = wav_file.with_suffix('.mp3')
        
        # Get original size
        original_size = wav_file.stat().st_size
        
        print(f"Converting: {wav_file.name}")
        print(f"  Original size: {original_size / (1024*1024):.1f} MB")
        
        if convert_wav_to_mp3(str(wav_file), str(mp3_file)):
            # Get new size
            new_size = mp3_file.stat().st_size
            saved = original_size - new_size
            total_saved += saved
            
            print(f"  New size: {new_size / (1024*1024):.1f} MB")
            print(f"  Space saved: {saved / (1024*1024):.1f} MB ({saved/original_size*100:.1f}%)\n")
            
            # Delete original WAV file
            wav_file.unlink()
            print(f"  ✓ Deleted original WAV file\n")
        else:
            print(f"  ✗ Conversion failed\n")
    
    print(f"\n✅ Conversion complete!")
    print(f"Total space saved: {total_saved / (1024*1024):.1f} MB")

if __name__ == "__main__":
    main()

