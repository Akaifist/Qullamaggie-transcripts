# YouTube Video Processor - Qullamaggie Livestream Analyzer

This tool downloads YouTube videos, removes silence, transcribes the audio, and generates a highlight summary for faster learning.

## Features

- 🎥 Downloads YouTube videos and extracts audio
- 🔇 Removes silence from audio to keep only active voice
- 📝 Transcribes audio using OpenAI Whisper
- 📊 Generates highlight summaries with timestamps
- 💾 Saves full transcription in JSON format

## Prerequisites

1. **Python 3.8+**
2. **FFmpeg** - Required for audio processing
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt-get install ffmpeg`
   - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure FFmpeg is installed and accessible in your PATH.

## Usage

```bash
python process_video.py <youtube_url>
```

Example:
```bash
python process_video.py https://youtu.be/VRdK05wyVhM?si=KwWVG4-U48WSpIdc
```

## Output

The script creates an organized folder structure for each video in the `videos/` directory:

```
videos/
└── Video_Title/
    ├── audio/
    │   └── Video_Title_processed_audio.mp3 (compressed, 32kbps)
    ├── summaries/
    │   └── Video_Title_summary.md
    └── transcriptions/
        └── Video_Title_transcription.json
```

All video folders are grouped together in the `videos/` directory (no gaps from other folders), making it easy to access. Each video folder contains organized subdirectories:
- **audio/** - Processed audio file with silence removed (MP3 format, 32kbps for maximum space efficiency)
- **summaries/** - Highlight summary with key points and full transcription
- **transcriptions/** - Full transcription with timestamps in JSON format

## Configuration

You can modify the silence removal parameters in `process_video.py`:

- `min_silence_len`: Minimum length of silence to split on (default: 1000ms)
- `silence_thresh`: Silence threshold in dB (default: -40)
- `keep_silence`: Amount of silence to keep at chunk boundaries (default: 200ms)

For Whisper model, you can change the model size:
- `tiny` - Fastest, least accurate
- `base` - Balanced (default)
- `small` - Better accuracy
- `medium` - High accuracy
- `large` - Best accuracy, slowest

## Notes

- First run will download the Whisper model (~150MB for base model)
- Processing time depends on video length and model size
- The script automatically handles video download and audio extraction
👤 Maintainer

@Akaifist

Building the most complete, structured archive of Qullamaggie’s teachings.

You can:
	•	Clone it
	•	Study it
	•	Add to it
	•	Train models on it

⸻

⚖️ License

Personal knowledge archive.
For education & research.
Not for resale.
