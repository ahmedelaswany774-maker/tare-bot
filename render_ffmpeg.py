"""Bounded-memory landscape renderer for long narration."""
import json
import subprocess
import tempfile
from pathlib import Path


def render_story(audio_path, clip_files, output_path):
    if not clip_files:
        raise RuntimeError("لم تُحمّل أي مشاهد؛ لن يتم إنشاء فيديو فارغ")
    duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", audio_path,
    ], text=True).strip())
    if duration <= 0:
        raise ValueError("مدة الصوت غير صالحة")
    with tempfile.TemporaryDirectory(prefix="story-render-") as folder:
        root = Path(folder)
        segments = []
        for index, path in enumerate(clip_files):
            target = root / f"scene-{index:04d}.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path,
                "-an", "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1,fps=25",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-threads", "2",
                "-pix_fmt", "yuv420p", str(target),
            ], check=True)
            segments.append(target)
            print(f"تجهيز المشهد {index + 1}/{len(clip_files)}", flush=True)
        listing = root / "scenes.txt"
        listing.write_text("".join(f"file '{path}'\n" for path in segments), encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", str(listing),
            "-i", audio_path, "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-t", str(duration), "-shortest", "-movflags", "+faststart", output_path,
        ], check=True)
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
        "-of", "json", output_path,
    ], text=True))
    if not {"audio", "video"}.issubset({stream["codec_type"] for stream in probe["streams"]}):
        raise RuntimeError("الفيديو الناتج لا يحتوي على صوت وصورة معًا")
    if abs(float(probe["format"]["duration"]) - duration) > 1:
        raise RuntimeError("مدة الفيديو لا تطابق مدة التعليق الصوتي")
    print(f"اكتمل الرندر: 1280x720، المدة {duration:.1f} ثانية", flush=True)
