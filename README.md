# 🎬 Clipper (Free & Low-Cost AI Short-Form Video Generator)

Turn long videos into viral, captioned 9:16 vertical clips (TikTok, Shorts, Reels) using **100% free / open-source resources**.

---

## 💡 Free Resource Architecture

| Step | Tool | Cost | Details |
|------|------|------|---------|
| **1. Video Ingest** | `yt-dlp` | **$0.00** | Open-source downloader for YouTube, Vimeo, Twitch, or local MP4 files. |
| **2. Audio Transcription** | `faster-whisper` | **$0.00** | Runs locally on CPU/GPU (`int8` quantization). Zero cloud API costs and provides word-level timestamps for karaoke captions. |
| **3. Viral Moment Detection** | **Google Gemini Flash** (via [Google AI Studio](https://aistudio.google.com/api-keys)) | **$0.00** | Uses the official Gemini API free tier (15 requests/min, up to 1M tokens/min, 1,500 reqs/day). |
| **4. Subtitle & Clip Rendering** | `FFmpeg` | **$0.00** | Local centre-crop to 9:16 and burning karaoke ASS subtitles. |

---

## 🚀 Quick Setup

### 1. Prerequisites
- **Python 3.10+**
- **FFmpeg** (Ensure `ffmpeg` is installed and on your PATH)

### 2. Install Dependencies
```bash
# Optional: create a virtual environment
python -m venv .venv
# Activate on Windows:
.\.venv\Scripts\Activate.ps1
# Activate on Mac/Linux:
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Get Your Free Gemini API Key
1. Go to [Google AI Studio API Keys](https://aistudio.google.com/api-keys).
2. Click **Create API key**.
3. Set your key in a `.env` file in the project folder:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
   *Alternatively, export it in your terminal:*
   - **PowerShell:** `$env:GEMINI_API_KEY="your_api_key_here"`
   - **CMD:** `set GEMINI_API_KEY=your_api_key_here`
   - **Bash/Zsh:** `export GEMINI_API_KEY="your_api_key_here"`

---

## ⚡ How to Run

### Example 1: YouTube Video
```bash
python clipper.py "https://www.youtube.com/watch?v=VIDEO_ID" --clips 3
```

### Example 2: Local Video File
```bash
python clipper.py ./my_podcast.mp4 --clips 5 --min 20 --max 60 --whisper base
```

### Options & Flags
- `--clips N`: Number of viral clips to find (default: `5`).
- `--min SEC`: Minimum clip length in seconds (default: `20`).
- `--max SEC`: Maximum clip length in seconds (default: `60`).
- `--whisper MODEL`: Whisper model size: `tiny`, `base`, `small`, `medium`, `large-v3` (default: `base` — fast on standard CPUs).
- `--model MODEL`: Gemini model (default: `gemini-2.5-flash` or `gemini-3.8-flash`).
- `--api-key KEY`: Pass API key directly if not in environment.
- `--work DIR`: Working & output folder (default: `./project`).

---

## 📁 Output & Workflow

Output files are stored in `./project/`:
- `./project/source.mp4`: Downloaded or copied source video.
- `./project/transcript.json`: Full cached transcript with word-level timestamps.
- `./project/clips.json`: Timestamped moments picked by Gemini. **You can edit this file manually and re-run to immediately re-export custom cuts!**
- `./project/clips/*.mp4`: Final vertical 9:16 videos with burned-in karaoke subtitles ready to post!
