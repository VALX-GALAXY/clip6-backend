#!/usr/bin/env python3
"""FastAPI Backend for Clipper: AI Short-Form Video Generator.
Supports local execution and cloud deployment (Hugging Face Spaces, Render, Railway, etc.).
"""
import asyncio
import concurrent.futures
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import clipper

load_dotenv()

app = FastAPI(
    title="VA Clipper AI API",
    description="VA Clipper AI: Turn long videos into viral 9:16 vertical clips",
    version="2.0.0"
)

# Enable CORS for Netlify and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "jobs"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# In-memory jobs tracking
jobs_db: Dict[str, Dict[str, Any]] = {}


class ClipRequest(BaseModel):
    url: str = Field(..., description="YouTube/Vimeo URL or local video path")
    clips_count: int = Field(default=3, ge=1, le=10, description="Number of clips to generate")
    min_duration: int = Field(default=20, ge=10, le=120, description="Minimum clip duration (seconds)")
    max_duration: int = Field(default=60, ge=15, le=180, description="Maximum clip duration (seconds)")
    whisper_model: str = Field(default="tiny", description="Whisper model: tiny, base, small")
    gemini_model: Optional[str] = Field(default=None, description="Gemini model override")
    api_key: Optional[str] = Field(default=None, description="Optional Gemini API key override")


def process_video_job(job_id: str, req: ClipRequest):
    job = jobs_db[job_id]
    job_dir = DATA_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    outdir = job_dir / "clips"
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        # Resolve API Key
        api_key = req.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key is required. Set GEMINI_API_KEY in .env or provide it in the request.")

        model = req.gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

        # 1. Fast-Path: Check for instant captions first (bypasses heavy video download and Whisper)
        job["status"] = "processing"
        job["step"] = "Checking instant captions from YouTube..."
        job["progress"] = 10
        transcript = None
        if re.match(r"https?://", req.url):
            transcript = clipper.fetch_youtube_subtitles(req.url, job_dir)

        if transcript:
            # 2. Moments detection with Gemini (2-3 seconds)
            job["step"] = "Finding viral moments with Google Gemini AI..."
            job["progress"] = 35
            clips_data = clipper.detect_moments(
                transcript,
                n=req.clips_count,
                lo=req.min_duration,
                hi=req.max_duration,
                api_key=api_key,
                model=model
            )
            if not clips_data:
                raise ValueError("No viral moments found matching duration criteria. Try adjusting min/max seconds.")

            # 3. Download optimized 720p stream
            job["step"] = "Downloading optimized video stream..."
            job["progress"] = 60
            video_path = clipper.ingest(req.url, job_dir)
        else:
            # Fallback path (no native captions or local upload)
            job["step"] = "Downloading / ingesting video..."
            job["progress"] = 20
            video_path = clipper.ingest(req.url, job_dir)

            job["step"] = f"Transcribing audio with Whisper ({req.whisper_model})..."
            job["progress"] = 50
            transcript = clipper.transcribe(video_path, job_dir, model_size=req.whisper_model, src_url=req.url)

            job["step"] = "Finding viral moments with Google Gemini AI..."
            job["progress"] = 70
            clips_data = clipper.detect_moments(
                transcript,
                n=req.clips_count,
                lo=req.min_duration,
                hi=req.max_duration,
                api_key=api_key,
                model=model
            )
            if not clips_data:
                raise ValueError("No viral moments found matching duration criteria. Try adjusting min/max seconds.")

        # 4. Export 9:16 clips with burned karaoke subtitles in parallel
        job["step"] = f"Exporting {len(clips_data)} vertical 9:16 clips (Turbo mode)..."
        job["progress"] = 75

        def render_clip_task(item):
            idx, c = item
            clip_file = clipper.export_clip(video_path, transcript, c, idx, outdir, job_dir)
            filename = clip_file.name
            duration = round(c["end"] - c["start"], 1)
            return {
                "index": idx,
                "title": c.get("title", f"Clip #{idx}"),
                "hook": c.get("hook", ""),
                "score": c.get("score", 90),
                "start": c["start"],
                "end": c["end"],
                "duration": duration,
                "filename": filename,
                "download_url": f"/api/clips/{job_id}/{filename}"
            }

        exported_clips = []
        max_workers = min(2, max(1, os.cpu_count() or 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {executor.submit(render_clip_task, (idx, c)): idx for idx, c in enumerate(clips_data, 1)}
            done_count = 0
            for fut in concurrent.futures.as_completed(future_to_item):
                clip_result = fut.result()
                exported_clips.append(clip_result)
                done_count += 1
                job["progress"] = 75 + int((done_count / len(clips_data)) * 23)

        exported_clips.sort(key=lambda x: x["index"])

        job["status"] = "completed"
        job["step"] = "Clips ready!"
        job["progress"] = 100
        job["clips"] = exported_clips

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["step"] = f"Error: {str(e)}"
        print(f"[Job {job_id} Error]: {e}")


@app.get("/api/health")
def health_check():
    has_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    return {
        "status": "healthy",
        "api_key_configured": has_key,
        "default_model": clipper.DEFAULT_MODEL
    }


@app.post("/api/process")
def start_clipping(req: ClipRequest, background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex[:8]
    jobs_db[job_id] = {
        "id": job_id,
        "status": "queued",
        "step": "Job queued...",
        "progress": 5,
        "url": req.url,
        "clips": [],
        "error": None
    }
    background_tasks.add_task(process_video_job, job_id, req)
    return {"job_id": job_id, "message": "Video processing started"}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs_db[job_id]


@app.get("/api/clips/{job_id}/{filename}")
def download_clip(job_id: str, filename: str):
    clip_path = DATA_DIR / job_id / "clips" / filename
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip file not found")
    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# Serve frontend static files if available
frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
