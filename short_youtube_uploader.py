import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import edge_tts
from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

METADATA_PATH = Path(os.environ.get("METADATA_PATH", "story_metadata.json"))
STATE_PATH = Path(os.environ.get("STATE_PATH", "upload_state.json"))
SHORT_STATE_PATH = Path("short_state.json")
SOURCE_VIDEO = Path(os.environ.get("SOURCE_VIDEO", "story.mp4"))
SHORT_VIDEO = Path("story_short.mp4")
VOICE_FILE = Path("teaser_voice.mp3")
CAPTION_DIR = Path("teaser_captions")
MAX_SECONDS = int(os.environ.get("SHORT_MAX_SECONDS", "50"))
WIDTH, HEIGHT = 1080, 1920


def save_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_caption_image(text, path):
    image = Image.new("RGBA", (WIDTH, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((30, 20, WIDTH - 30, 280), radius=24, fill=(0, 0, 0, 190))
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > 27 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    lines = [get_display(arabic_reshaper.reshape(line)) for line in lines[:3]]
    boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=2) for line in lines]
    total_height = sum(b[3] - b[1] for b in boxes) + 12 * max(0, len(lines) - 1)
    y = (300 - total_height) // 2
    for line, box in zip(lines, boxes):
        tw, th = box[2] - box[0], box[3] - box[1]
        draw.text(((WIDTH - tw) // 2, y), line, font=font, fill="white",
                  stroke_width=2, stroke_fill="black")
        y += th + 12
    image.save(path)


def render_teaser(teaser):
    if not SOURCE_VIDEO.exists():
        raise FileNotFoundError("story.mp4 is missing")
    async def make_voice():
        await edge_tts.Communicate(teaser, "ar-EG-ShakirNeural").save(str(VOICE_FILE))
    asyncio.run(make_voice())
    voice = AudioFileClip(str(VOICE_FILE))
    duration = min(float(MAX_SECONDS), voice.duration)
    source = VideoFileClip(str(SOURCE_VIDEO))
    if source.duration < duration:
        raise ValueError("Source story video is shorter than the teaser narration")

    # Select shots from across the full story, rather than reusing only its opening.
    count = max(5, min(9, int(duration // 5)))
    part = duration / count
    clips = []
    max_start = max(0.0, source.duration - part)
    for i in range(count):
        start = max_start * i / max(1, count - 1)
        clip = source.subclipped(start, start + part).resized(height=HEIGHT)
        if clip.w < WIDTH:
            clip = clip.resized(width=WIDTH)
        clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=WIDTH, height=HEIGHT)
        clips.append(clip)
    montage = concatenate_videoclips(clips, method="compose").with_duration(duration).with_audio(voice.subclipped(0, duration))

    CAPTION_DIR.mkdir(exist_ok=True)
    sentences = [s.strip() for s in re.split(r"(?<=[.!؟?])\s+", teaser) if s.strip()]
    if not sentences:
        sentences = [teaser]
    weights = [max(1, len(s.split())) for s in sentences]
    total_weight = sum(weights)
    overlays, cursor = [], 0.0
    for i, (sentence, weight) in enumerate(zip(sentences, weights)):
        seg_duration = duration * weight / total_weight
        image_path = CAPTION_DIR / f"caption_{i:02d}.png"
        make_caption_image(sentence, image_path)
        overlays.append(ImageClip(str(image_path)).with_start(cursor).with_duration(seg_duration).with_position(("center", "bottom")))
        cursor += seg_duration
    final = CompositeVideoClip([montage, *overlays], size=(WIDTH, HEIGHT)).with_duration(duration).with_audio(voice.subclipped(0, duration))
    final.write_videofile(str(SHORT_VIDEO), fps=30, codec="libx264", audio_codec="aac",
                          preset="veryfast", threads=4, ffmpeg_params=["-crf", "22", "-movflags", "+faststart"])
    final.close()
    montage.close()
    source.close()
    voice.close()
    for clip in clips:
        clip.close()


def main():
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    long_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    long_video_id = long_state.get("youtube_video_id")
    if not long_video_id:
        raise ValueError("Long video upload is missing; refusing to publish a teaser")
    teaser = metadata.get("teaser_script", "").strip()
    if not teaser:
        raise ValueError("Missing teaser_script; refusing to upload a raw crop")
    render_teaser(teaser)

    creds = Credentials.from_authorized_user_info(
        json.loads(os.environ["YT_TOKEN_JSON"]),
        ["https://www.googleapis.com/auth/youtube.upload"],
    )
    creds.refresh(Request())
    youtube = build("youtube", "v3", credentials=creds)
    long_url = f"https://www.youtube.com/watch?v={long_video_id}"
    title = f"{metadata.get('short_title') or metadata['title']} | #Shorts"
    source_lines = "\n".join(
        f"- {s.get('title', 'مصدر')} — {s.get('publisher', '')}: {s.get('url', '')}"
        for s in metadata.get("sources", [])
    )
    description = (
        f"🎬 شاهد القصة الكاملة: {long_url}\n\n"
        f"الحلقة {metadata.get('episode_number', '')} من سلسلة {metadata.get('series_title', 'قصص واقعيه')}.\n"
        "هذا مقطع تشويقي ولا يكشف نهاية القصة.\n\n"
        f"المصادر:\n{source_lines}\n\n#قصص_واقعية #قصص_حقيقية #Shorts"
    )
    scheduled = long_state.get("scheduled_publish_at")
    status = {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    if scheduled:
        dt = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
        if dt > datetime.now(timezone.utc):
            status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "publishAt": scheduled}

    response = youtube.videos().insert(
        part="snippet,status",
        body={"snippet": {
            "title": title[:100], "description": description[:5000],
            "tags": metadata.get("tags", []) + ["Shorts", "قصص واقعية", "القصة الكاملة"],
            "categoryId": "24",
        }, "status": status},
        media_body=MediaFileUpload(str(SHORT_VIDEO), mimetype="video/mp4", resumable=True),
    ).execute()
    short_id = response["id"]
    save_json(SHORT_STATE_PATH, {
        "status": "uploaded", "short_video_id": short_id,
        "related_long_video_id": long_video_id, "episode_id": metadata.get("episode_id"),
        "episode_number": metadata.get("episode_number"), "video": str(SHORT_VIDEO),
        "scheduled_publish_at": scheduled if status["privacyStatus"] == "private" else None,
        "teaser_script": teaser,
    })
    print(f"تم رفع الريلز التشويقي: https://youtube.com/shorts/{short_id}")
    print(f"رابط الفيديو الكامل في الوصف: {long_url}")


if __name__ == "__main__":
    main()
