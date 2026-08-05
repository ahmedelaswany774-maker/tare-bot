"""
Kaggle worker: renders the final story video from pre-fetched clips + audio.
Runs on a Kaggle GPU kernel so the CPU-bound frame encoding that's slow on
GitHub Actions gets a faster machine, and uses NVENC hardware encoding when
the environment supports it (falls back to libx264 automatically if not).

Expects these files to be sitting next to this script (uploaded alongside it
by kaggle_client.py):
  - story.mp3
  - clip_00.mp4, clip_01.mp4, ... (in order)
  - manifest.json  ->  {"target_duration": <float>}
"""

import json
import math
import os
import subprocess
import sys

try:
    from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "moviepy"], check=True)
    from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = "/kaggle/working/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(os.path.join(HERE, "manifest.json"), "r", encoding="utf-8") as f:
    manifest = json.load(f)
target_duration = manifest["target_duration"]

clip_files = sorted(
    f for f in os.listdir(HERE) if f.startswith("clip_") and f.endswith(".mp4")
)
clip_files = [os.path.join(HERE, f) for f in clip_files]
print(f"وجدت {len(clip_files)} كليب")

audio_clip = AudioFileClip(os.path.join(HERE, "story.mp3"))

video_clips = [VideoFileClip(f).resized(width=1280) for f in clip_files]
final_video = concatenate_videoclips(video_clips, method="chain")

if final_video.duration < target_duration:
    loops_needed = math.ceil(target_duration / final_video.duration)
    final_video = concatenate_videoclips([final_video] * loops_needed, method="chain")

final_video = final_video.subclipped(0, target_duration)
final_video = final_video.with_audio(audio_clip)

output_path = os.path.join(OUTPUT_DIR, "story.mp4")


def _nvenc_available():
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


if _nvenc_available():
    print("✅ h264_nvenc متاح، هنستخدم تسريع الـ GPU")
    try:
        final_video.write_videofile(
            output_path,
            fps=25,
            codec="h264_nvenc",
            audio_codec="aac",
            threads=4,
            ffmpeg_params=["-preset", "p1", "-cq", "23"],
        )
    except Exception as e:
        print(f"⚠️ فشل الترميز بـ NVENC ({e})، هنرجع لـ libx264 على الـ CPU")
        final_video.write_videofile(
            output_path, fps=25, codec="libx264", audio_codec="aac",
            preset="veryfast", threads=4, ffmpeg_params=["-crf", "23"],
        )
else:
    print("ℹ️ h264_nvenc غير متاح هنا، هنستخدم libx264 على الـ CPU (بس على معالج Kaggle)")
    final_video.write_videofile(
        output_path, fps=25, codec="libx264", audio_codec="aac",
        preset="veryfast", threads=4, ffmpeg_params=["-crf", "23"],
    )

print(f"DONE -> {output_path}")
