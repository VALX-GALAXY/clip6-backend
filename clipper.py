#!/usr/bin/env python3
"""clipper: long video -> transcript -> best moments -> captioned 9:16 clips.
Powered by Google Gemini (Google AI Studio - Free Tier) and faster-whisper.

Usage:
  Interactive mode:
    python clipper.py
  CLI mode:
    python clipper.py "https://youtube.com/watch?v=..." --clips 5
    python clipper.py ./podcast.mp4 --clips 3 --min 20 --max 60
"""
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Gemini models with automatic failover (handles temporary 503 high demand spikes)
MODELS_TO_TRY = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", MODELS_TO_TRY[0])


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"Command failed: {' '.join(str(c) for c in cmd)}\n{r.stderr[-1500:]}")
    return r.stdout


def get_api_key(args_key: str | None = None) -> str:
    key = args_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        sys.exit(
            "\n[Error] Gemini API key not found!\n\n"
            "To use this clipper with free resources from Google AI Studio:\n"
            "1. Get your free key at: https://aistudio.google.com/api-keys\n"
            "2. Add it to .env: GEMINI_API_KEY=AIzaSy...\n"
        )
    return key


# ---------------------------------------------------------------- 1. ingest
def ingest(src: str, work: Path) -> Path:
    out = work / "source.mp4"
    if out.exists():
        print(f"  Found cached video at {out}")
        return out
    if re.match(r"https?://", src):
        print(f"  Downloading video with yt-dlp (fast H.264/AAC streams): {src}")
        # Prefer H.264 (avc1) + AAC for 5x faster CPU decoding and native AAC audio
        run([sys.executable, "-m", "yt_dlp",
             "--concurrent-fragments", "5",
             "-f", "bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/bv*[height<=1080]+ba/b",
             "--merge-output-format", "mp4",
             "-o", str(out), src])
    else:
        src_path = Path(src)
        if not src_path.exists():
            sys.exit(f"Source video file not found: {src}")
        shutil.copy(src, out)
    return out


# ------------------------------------------------------------ 2. transcribe
def fetch_youtube_subtitles(src: str, work: Path) -> dict | None:
    """Attempts to fetch pre-existing YouTube captions in seconds, bypassing Whisper."""
    if not re.match(r"https?://", src):
        return None
    try:
        print("  Checking for instant YouTube captions...")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--write-auto-sub", "--write-sub",
            "--sub-lang", "en.*,en",
            "--sub-format", "json3",
            "--skip-download",
            "-o", str(work / "subtitles.%(ext)s"),
            src
        ]
        subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=25)
        json3_files = list(work.glob("subtitles*.json3"))
        if json3_files:
            raw = json.loads(json3_files[0].read_text(encoding="utf-8"))
            segments = []
            for ev in raw.get("events", []):
                if "segs" not in ev:
                    continue
                start_sec = ev.get("tStartMs", 0) / 1000.0
                dur_sec = ev.get("dDurationMs", 0) / 1000.0
                end_sec = start_sec + dur_sec
                words = []
                text_parts = []
                for s in ev["segs"]:
                    w = s.get("utf8", "").strip()
                    if not w:
                        continue
                    text_parts.append(w)
                    w_start = start_sec + (s.get("tOffsetMs", 0) / 1000.0)
                    words.append({"w": w, "start": round(w_start, 2), "end": round(w_start + 0.35, 2)})
                if text_parts:
                    segments.append({
                        "start": round(start_sec, 2),
                        "end": round(end_sec, 2),
                        "text": " ".join(text_parts),
                        "words": words
                    })
            if segments:
                data = {"language": "en", "segments": segments}
                (work / "transcript.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                print("  ⚡ Instant transcript loaded from YouTube in 1 second! (Whisper bypassed)")
                return data
    except Exception as e:
        print(f"  Note: Native captions check skipped ({e}), using local Whisper...")
    return None


def transcribe(video: Path, work: Path, model_size: str = "base", src_url: str | None = None) -> dict:
    tpath = work / "transcript.json"
    if tpath.exists():
        print(f"  Loading cached transcript from {tpath}")
        return json.loads(tpath.read_text(encoding="utf-8"))
    
    # 1. Fast-path: Check for instant YouTube captions
    if src_url:
        yt_subs = fetch_youtube_subtitles(src_url, work)
        if yt_subs:
            return yt_subs
    
    # 2. Fallback: Local faster-whisper
    from faster_whisper import WhisperModel  # lazy: heavy import
    wav = work / "audio.wav"
    print("  Extracting audio for local Whisper...")
    run(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    print(f"  Running local faster-whisper ({model_size} model, int8, beam_size=1)...")
    model = WhisperModel(model_size, compute_type="int8")
    segs, info = model.transcribe(str(wav), beam_size=1, word_timestamps=True, vad_filter=True)
    data = {"language": info.language, "segments": []}
    for s in segs:
        data["segments"].append({
            "start": s.start, "end": s.end, "text": s.text.strip(),
            "words": [{"w": w.word.strip(), "start": w.start, "end": w.end} for w in s.words],
        })
    tpath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


# --------------------------------------------------------- 3. detect moments
PROMPT = """You are a viral short-form video editor for TikTok, YouTube Shorts, and Instagram Reels.
Below is a timestamped transcript of a video.
Analyze the transcript and identify the {n} most engaging, high-retention viral moments.

Each selected moment must:
- Be between {lo} and {hi} seconds long
- Open with a powerful hook or punchy statement that grabs viewer attention in the first 3 seconds
- Be self-contained and convey a complete idea, story, debate, or payoff (no missing context)
- End on a natural finish or impactful conclusion, never cut off mid-sentence
- Not overlap with any other selected moment

Score each moment 0-100 based on virality and retention potential.

Respond ONLY with a valid JSON array in the following format (no explanations, no markdown fences):
[
  {{
    "start": 12.5,
    "end": 45.0,
    "title": "Short catchy title",
    "hook": "Opening hook sentence",
    "score": 92
  }}
]

TRANSCRIPT:
{tx}"""


def call_gemini(prompt: str, api_key: str, preferred_model: str) -> str:
    """Calls Google Gemini API with automatic fallback if primary model is unavailable."""
    models_queue = [preferred_model] + [m for m in MODELS_TO_TRY if m != preferred_model]
    
    # Try google-genai SDK first
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        
        for m in models_queue:
            try:
                print(f"  Querying Gemini ({m})...")
                config = types.GenerateContentConfig(response_mime_type="application/json")
                resp = client.models.generate_content(model=m, contents=prompt, config=config)
                if resp.text:
                    return resp.text
            except Exception as e:
                err_str = str(e)
                print(f"  Note: {m} encountered: {err_str[:120]}... trying next model.")
                continue
    except ImportError:
        pass

    # Direct REST API fallback via standard library urllib
    import urllib.request
    for m in models_queue:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            continue

    sys.exit("\n[Error] Unable to reach Gemini API models. Please check your network and API key.")


def detect_moments(tr: dict, n: int, lo: int, hi: int, api_key: str, model: str) -> list:
    tx = "\n".join(f"[{s['start']:.1f}] {s['text']}" for s in tr["segments"])
    prompt = PROMPT.format(n=n, lo=lo, hi=hi, tx=tx)
    raw = call_gemini(prompt, api_key=api_key, preferred_model=model)
    raw = re.sub(r"^```(?:json)?", "", raw.strip(), flags=re.M)
    raw = re.sub(r"```$", "", raw.strip(), flags=re.M).strip()
    match = re.search(r"\[\s*\{.*\}\s*\]", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    return normalize_clips(json.loads(raw), tr, lo, hi)


def normalize_clips(clips: list, tr: dict, lo: int, hi: int) -> list:
    """Snap LLM timestamps to word boundaries, enforce length, drop overlaps."""
    words = [w for s in tr["segments"] for w in s["words"]]
    if not words:
        return []
    out = []
    for c in sorted(clips, key=lambda c: -c.get("score", 0)):
        start = min(words, key=lambda w: abs(w["start"] - c["start"]))["start"]
        end = min(words, key=lambda w: abs(w["end"] - c["end"]))["end"]
        if end - start > hi:  # trim to last word that fits
            end = max(w["end"] for w in words if start < w["end"] <= start + hi)
        if end - start < lo * 0.5:
            continue
        if any(start < o["end"] and end > o["start"] for o in out):
            continue
        out.append({**c, "start": round(start, 2), "end": round(end + 0.15, 2)})
    return sorted(out, key=lambda c: c["start"])


# ------------------------------------------------------------- 4. captions
def ass_time(t: float) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def build_ass(tr: dict, start: float, end: float, path: Path, per_line: int = 4):
    """Karaoke-style captions: the active word turns yellow."""
    words = [w for s in tr["segments"] for w in s["words"] if w["start"] >= start and w["end"] <= end]
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
        "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,"
        "Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        # Primary = highlighted (yellow), Secondary = not-yet-spoken (white); colours are &HAABBGGRR
        "Style: Default,Arial,84,&H0000FFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,6,2,2,60,60,520,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = []
    for i in range(0, len(words), per_line):
        grp = words[i:i + per_line]
        text = "".join(f"{{\\k{max(int((w['end'] - w['start']) * 100), 1)}}}{w['w'].upper()} " for w in grp)
        lines.append(f"Dialogue: 0,{ass_time(grp[0]['start'] - start)},{ass_time(grp[-1]['end'] - start)},"
                     f"Default,,0,0,0,,{text.strip()}")
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------- 5. export
def export_clip(video: Path, tr: dict, clip: dict, idx: int, outdir: Path, work: Path) -> Path:
    ass = work / f"clip{idx}.ass"
    build_ass(tr, clip["start"], clip["end"], ass)
    slug = re.sub(r"[^a-z0-9]+", "-", clip.get("title", "clip").lower()).strip("-")[:40]
    out = outdir / f"{idx:02d}-{slug}.mp4"
    duration = round(clip["end"] - clip["start"], 2)
    
    # Centre-crop to 9:16 and burn captions
    vf = f"crop=ih*9/16:ih,scale=1080:1920,ass={ass.name}"
    
    # Normalize audio loudness to standard social media volume (-14 LUFS) and boost dialogue
    af = "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"

    # FFmpeg export:
    # -avoid_negative_ts make_zero fixes negative audio PTS that causes silent playback in players
    # -async 1 guarantees audio frame sync
    # -map 0:v:0 -map 0:a:0? ensures audio stream is always included
    run([
        "ffmpeg", "-y",
        "-ss", str(clip["start"]),
        "-i", str(video.resolve()),
        "-t", str(duration),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-threads", "0",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-avoid_negative_ts", "make_zero",
        "-async", "1",
        "-movflags", "+faststart",
        str(out.resolve())
    ], cwd=work)
    return out


# --------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", default=None, help="YouTube/Vimeo/Twitch URL or local video path")
    ap.add_argument("--clips", type=int, default=5, help="Number of viral clips to find (default: 5)")
    ap.add_argument("--min", type=int, default=20, dest="lo", help="Minimum clip duration in seconds (default: 20)")
    ap.add_argument("--max", type=int, default=60, dest="hi", help="Maximum clip duration in seconds (default: 60)")
    ap.add_argument("--whisper", default="base", help="Whisper model size: tiny/base/small/medium/large-v3 (default: base)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model to use (default: {DEFAULT_MODEL})")
    ap.add_argument("--api-key", default=None, help="Google Gemini API key (or set GEMINI_API_KEY env var)")
    ap.add_argument("--work", default="./project", help="Working + output directory (default: ./project)")
    a = ap.parse_args()

    # Interactive prompt if source is not provided via argument
    if not a.source:
        print("=" * 60)
        print("🎬 CLIPPER: AI Short-Form Video Generator (Free Tier)")
        print("=" * 60)
        try:
            a.source = input("\n🎥 Enter YouTube URL or local video path: ").strip()
            if not a.source:
                sys.exit("Error: No video source provided.")
            clips_in = input("✂️  How many clips would you like? (Press Enter for 5): ").strip()
            if clips_in.isdigit():
                a.clips = int(clips_in)
        except (EOFError, KeyboardInterrupt):
            sys.exit("\nExiting.")

    api_key = get_api_key(a.api_key)

    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    outdir = work / "clips"; outdir.mkdir(exist_ok=True)

    print("\n1/4 Ingesting video...")
    video = ingest(a.source, work)
    print("2/4 Transcribing audio (instant captions or Whisper)...")
    tr = transcribe(video, work, a.whisper, src_url=a.source)
    print("3/4 Finding viral moments with Google Gemini AI...")
    cpath = work / "clips.json"
    clips = json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else detect_moments(tr, a.clips, a.lo, a.hi, api_key, a.model)
    cpath.write_text(json.dumps(clips, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"4/4 Exporting {len(clips)} vertical 9:16 clips with karaoke subtitles...")
    for i, c in enumerate(clips, 1):
        p = export_clip(video, tr, c, i, outdir, work)
        print(f"  [{c.get('score', '?')}] {c['start']:.0f}s-{c['end']:.0f}s  {c.get('title', '')}  -> {p}")
    print(f"\n✨ Done! Clips are saved in: {outdir.resolve()}")


if __name__ == "__main__":
    main()
