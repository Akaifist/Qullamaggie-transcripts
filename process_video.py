#!/usr/bin/env python3
"""
YouTube Video Processor: Downloads video, removes silence, transcribes, and summarizes.
"""

import os
import sys
import json
import re
import shutil
from pathlib import Path
from typing import Tuple, Optional, Dict
import subprocess
try:
    import yt_dlp
except ImportError as e:
    print(f"Error: Missing required package. Please install dependencies: pip install -r requirements.txt")
    print(f"Missing: {e}")
    sys.exit(1)

# Try to import pydub, but make it optional - use ffmpeg directly if unavailable
PYDUB_AVAILABLE = False
try:
    from pydub import AudioSegment
    from pydub.silence import split_on_silence
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

# Try to import whisper - make it optional
WHISPER_AVAILABLE = False
WHISPER_TYPE = None
try:
    import whisper
    WHISPER_AVAILABLE = True
    WHISPER_TYPE = "standard"
except ImportError:
    try:
        from faster_whisper import WhisperModel
        WHISPER_AVAILABLE = True
        WHISPER_TYPE = "faster"
    except ImportError:
        WHISPER_AVAILABLE = False
        WHISPER_TYPE = None


def sanitize_filename(title: str) -> str:
    """Sanitize video title for use in filenames."""
    # Remove or replace invalid filename characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    # Replace spaces with underscores
    sanitized = re.sub(r'\s+', '_', sanitized)
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    # Limit length to avoid filesystem issues
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized


def download_video(url: str, output_dir: str = "downloads") -> Tuple[str, str]:
    """Download YouTube video and extract audio."""
    Path(output_dir).mkdir(exist_ok=True)
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '32',  # 32kbps for speech - maximum space savings
        }],
        'quiet': True,
        'no_warnings': True,
    }
    
    print(f"Downloading video from {url}...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'video')
        filename = ydl.prepare_filename(info)
        # Replace extension with mp3
        audio_file = os.path.splitext(filename)[0] + '.mp3'
    
    # Verify file exists
    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found after download: {audio_file}")
    
    print(f"Downloaded: {audio_file}")
    return audio_file, title


def remove_silence(audio_file: str, output_file: str, 
                   min_silence_len: int = 1000, 
                   silence_thresh: int = -40,
                   keep_silence: int = 200) -> str:
    """
    Remove silence from audio file using ffmpeg or pydub.
    
    Args:
        audio_file: Input audio file path
        output_file: Output audio file path
        min_silence_len: Minimum length of silence to split on (ms)
        silence_thresh: Silence threshold in dB
        keep_silence: Amount of silence to keep at the beginning/end of chunks (ms)
    """
    if PYDUB_AVAILABLE:
        print("Loading audio file...")
        # Support both wav and mp3 input
        if audio_file.endswith('.mp3'):
            audio = AudioSegment.from_mp3(audio_file)
        else:
            audio = AudioSegment.from_wav(audio_file)
        
        print("Removing silence...")
        # Split on silence
        chunks = split_on_silence(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh,
            keep_silence=keep_silence
        )
        
        if not chunks:
            print("No audio chunks found. Using original audio.")
            # Export as MP3 with very low bitrate to save space (32kbps for speech)
            audio.export(output_file, format="mp3", bitrate="32k")
            return output_file
        
        # Combine all non-silent chunks
        combined = AudioSegment.empty()
        for chunk in chunks:
            combined += chunk
        
        original_duration = len(audio) / 1000
        processed_duration = len(combined) / 1000
        print(f"Original duration: {original_duration:.1f}s")
        print(f"After silence removal: {processed_duration:.1f}s")
        if len(audio) > 0:
            reduction_pct = ((len(audio) - len(combined)) / len(audio)) * 100
            print(f"Reduction: {reduction_pct:.1f}%")
        else:
            print("Reduction: 0.0%")
        
        # Export as MP3 with very low bitrate (32kbps) to save space
        combined.export(output_file, format="mp3", bitrate="32k")
        print(f"Saved processed audio to: {output_file}")
        return output_file
    else:
        # Use ffmpeg directly for silence removal
        print("Using ffmpeg for silence removal...")
        # ffmpeg filter to remove silence
        # silenceremove=start_periods=1:start_duration=1:start_threshold=-40dB:detection=peak
        # aformat=dblp,areverse,silenceremove=start_periods=1:start_duration=1:start_threshold=-40dB:detection=peak,aformat=dblp,areverse
        
        # Convert threshold from dB to linear scale for ffmpeg
        # ffmpeg uses -50dB to -20dB range typically
        threshold_db = silence_thresh
        
        # Use MP3 format with very low bitrate (32kbps) to save space
        cmd = [
            'ffmpeg', '-i', audio_file,
            '-af', f'silenceremove=start_periods=1:start_duration={min_silence_len/1000}:start_threshold={threshold_db}dB:detection=peak',
            '-acodec', 'libmp3lame',
            '-ab', '32k',  # 32kbps bitrate for speech (maximum space savings)
            '-ar', '16000',  # Lower sample rate for speech (saves more space)
            '-y',  # Overwrite output file
            output_file
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"Silence removed using ffmpeg")
            print(f"Saved processed audio to: {output_file}")
            return output_file
        except subprocess.CalledProcessError as e:
            print(f"⚠️  FFmpeg silence removal failed: {e.stderr}")
            print("   Copying original audio file...")
            shutil.copy2(audio_file, output_file)
            return output_file
        except FileNotFoundError:
            print("⚠️  FFmpeg not found. Copying original audio file...")
            print("   Install ffmpeg: brew install ffmpeg")
            shutil.copy2(audio_file, output_file)
            return output_file


def transcribe_audio(audio_file: str, model_name: str = "base") -> Optional[list[dict]]:
    """
    Transcribe audio using Whisper.
    
    Returns:
        List of segments with 'start', 'end', and 'text' keys, or None if transcription unavailable
    """
    if not WHISPER_AVAILABLE:
        print("⚠️  Whisper not available. Skipping transcription.")
        print("   To enable transcription, install: pip install openai-whisper")
        print("   Or use: pip install faster-whisper")
        return None
    
    try:
        if WHISPER_TYPE == "faster":
            print(f"Loading Faster Whisper model ({model_name})...")
            from faster_whisper import WhisperModel
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            
            print("Transcribing audio...")
            segments_gen, _ = model.transcribe(audio_file, word_timestamps=False)
            
            segments = []
            for segment in segments_gen:
                segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip()
                })
        else:
            print(f"Loading Whisper model ({model_name})...")
            model = whisper.load_model(model_name)
            
            print("Transcribing audio...")
            result = model.transcribe(audio_file, word_timestamps=False)
            
            segments = []
            for segment in result["segments"]:
                segments.append({
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"].strip()
                })
        
        print(f"Transcribed {len(segments)} segments")
        return segments
    except Exception as e:
        print(f"⚠️  Transcription failed: {e}")
        print("   Continuing without transcription...")
        return None


def load_checkpoint(video_folder: str) -> Dict:
    """Load checkpoint file if it exists."""
    checkpoint_file = os.path.join(video_folder, ".checkpoint.json")
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_checkpoint(video_folder: str, state: Dict):
    """Save checkpoint file with current state."""
    checkpoint_file = os.path.join(video_folder, ".checkpoint.json")
    try:
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save checkpoint: {e}")


def generate_summary(segments: list[dict], title: str) -> str:
    """Generate a highlight summary from transcription segments."""
    if not segments:
        return f"# Video Summary: {title}\n\nNo transcription available."
    
    # Calculate total duration
    if 'end' not in segments[-1]:
        return f"# Video Summary: {title}\n\nInvalid transcription data."
    
    total_duration = segments[-1]['end']
    hours = int(total_duration // 3600)
    minutes = int((total_duration % 3600) // 60)
    seconds = int(total_duration % 60)
    
    # Create summary with timestamps for key points
    summary_lines = [f"# Video Summary: {title}\n\n"]
    summary_lines.append(f"**Total Duration:** {hours:02d}:{minutes:02d}:{seconds:02d}\n")
    summary_lines.append(f"**Total Segments:** {len(segments)}\n\n")
    
    summary_lines.append("## 🎯 Key Highlights\n\n")
    
    # Create highlights by grouping segments intelligently
    # Group segments that are close together and create highlights every ~60 seconds
    highlight_interval = 60  # seconds
    current_time = 0
    highlight_count = 0
    current_highlight_text = []
    current_highlight_start = 0
    
    for i, segment in enumerate(segments):
        # Start a new highlight if enough time has passed or at the beginning
        if segment["start"] - current_time > highlight_interval or i == 0:
            # Save previous highlight if it exists
            if current_highlight_text and i > 0:
                minutes_start = int(current_highlight_start // 60)
                seconds_start = int(current_highlight_start % 60)
                minutes_end = int(current_time // 60)
                seconds_end = int(current_time % 60)
                highlight_text = " ".join(current_highlight_text)
                summary_lines.append(
                    f"### [{minutes_start:02d}:{seconds_start:02d} - {minutes_end:02d}:{seconds_end:02d}] "
                    f"Highlight {highlight_count}\n\n"
                )
                summary_lines.append(f"{highlight_text}\n\n")
                highlight_count += 1
            
            # Start new highlight
            current_highlight_text = [segment["text"]]
            current_highlight_start = segment["start"]
            current_time = segment["end"]
        else:
            # Add to current highlight
            current_highlight_text.append(segment["text"])
            current_time = segment["end"]
    
    # Don't forget the last highlight
    if current_highlight_text:
        minutes_start = int(current_highlight_start // 60)
        seconds_start = int(current_highlight_start % 60)
        minutes_end = int(segments[-1]["end"] // 60)
        seconds_end = int(segments[-1]["end"] % 60)
        highlight_text = " ".join(current_highlight_text)
        summary_lines.append(
            f"### [{minutes_start:02d}:{seconds_start:02d} - {minutes_end:02d}:{seconds_end:02d}] "
            f"Highlight {highlight_count + 1}\n\n"
        )
        summary_lines.append(f"{highlight_text}\n\n")
    
    # Add full transcription
    summary_lines.append("---\n\n")
    summary_lines.append("## 📝 Full Transcription\n\n")
    for segment in segments:
        minutes = int(segment["start"] // 60)
        seconds = int(segment["start"] % 60)
        summary_lines.append(f"**[{minutes:02d}:{seconds:02d}]** {segment['text']}\n\n")
    
    return "".join(summary_lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_video.py <youtube_url>")
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Base directories
    downloads_dir = "downloads"
    videos_dir = "videos"
    Path(downloads_dir).mkdir(exist_ok=True)
    Path(videos_dir).mkdir(exist_ok=True)
    
    try:
        # Step 1: Download video (with auto-save check)
        audio_file, title = download_video(url, downloads_dir)
        
        # Sanitize title for folder and filenames
        safe_title = sanitize_filename(title)
        
        # Create a dedicated folder for this video in the videos/ directory
        video_folder = os.path.join(videos_dir, safe_title)
        Path(video_folder).mkdir(exist_ok=True)
        
        # Create subdirectories for organization
        audio_dir = os.path.join(video_folder, "audio")
        summaries_dir = os.path.join(video_folder, "summaries")
        transcriptions_dir = os.path.join(video_folder, "transcriptions")
        
        Path(audio_dir).mkdir(exist_ok=True)
        Path(summaries_dir).mkdir(exist_ok=True)
        Path(transcriptions_dir).mkdir(exist_ok=True)
        
        # Load checkpoint to see what's already done
        checkpoint = load_checkpoint(video_folder)
        processed_audio = os.path.join(audio_dir, f"{safe_title}_processed_audio.mp3")
        transcription_file = os.path.join(transcriptions_dir, f"{safe_title}_transcription.json")
        summary_file = os.path.join(summaries_dir, f"{safe_title}_summary.md")
        
        print(f"\n📁 Folder: {video_folder}/")
        
        # Update checkpoint - download complete
        checkpoint['downloaded'] = True
        checkpoint['url'] = url
        checkpoint['title'] = title
        save_checkpoint(video_folder, checkpoint)
        
        # Step 2: Remove silence (with auto-save check)
        if os.path.exists(processed_audio) and checkpoint.get('silence_removed', False):
            print("✓ Silence removal already completed (using existing file)")
        else:
            print("🔄 Removing silence from audio...")
            remove_silence(audio_file, processed_audio)
            checkpoint['silence_removed'] = True
            save_checkpoint(video_folder, checkpoint)
            print("✓ Silence removal saved")
        
        # Step 3: Transcribe (with auto-save check)
        segments = None
        if os.path.exists(transcription_file) and checkpoint.get('transcribed', False):
            print("✓ Transcription already completed (loading existing file)")
            try:
                with open(transcription_file, "r", encoding="utf-8") as f:
                    segments = json.load(f)
                print(f"✓ Loaded {len(segments)} segments from saved transcription")
            except Exception as e:
                print(f"⚠️  Could not load saved transcription: {e}")
                print("🔄 Re-transcribing...")
                segments = transcribe_audio(processed_audio)
        else:
            print("🔄 Transcribing audio...")
            segments = transcribe_audio(processed_audio)
        
        if segments:
            # Auto-save transcription immediately
            with open(transcription_file, "w", encoding="utf-8") as f:
                json.dump(segments, f, indent=2, ensure_ascii=False)
            checkpoint['transcribed'] = True
            save_checkpoint(video_folder, checkpoint)
            print(f"✓ Transcription auto-saved to: {transcription_file}")
            
            # Step 4: Generate summary (with auto-save check)
            if os.path.exists(summary_file) and checkpoint.get('summary_generated', False):
                print("✓ Summary already generated (using existing file)")
            else:
                print("🔄 Generating summary...")
                summary = generate_summary(segments, title)
                with open(summary_file, "w", encoding="utf-8") as f:
                    f.write(summary)
                checkpoint['summary_generated'] = True
                save_checkpoint(video_folder, checkpoint)
                print(f"✓ Summary auto-saved to: {summary_file}")
        else:
            print("\n⚠️  Transcription skipped. Audio processing complete.")
            print("   Install whisper to enable transcription:")
            print("   pip install openai-whisper")
        
        # Mark as complete
        checkpoint['completed'] = True
        save_checkpoint(video_folder, checkpoint)
        
        print("\n✅ Processing complete!")
        print(f"📁 All files organized in: {video_folder}/")
        print(f"   ├── audio/{safe_title}_processed_audio.mp3 (compressed, 32kbps)")
        if segments:
            print(f"   ├── transcriptions/{safe_title}_transcription.json")
            print(f"   └── summaries/{safe_title}_summary.md")
        print(f"\n💾 Auto-save enabled - all progress saved automatically")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        print("💾 Progress has been auto-saved. Run the script again to resume.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        print("\n💾 Progress has been auto-saved. Fix the error and run again to resume.")
        sys.exit(1)


if __name__ == "__main__":
    main()

