import os
import json
import math
import asyncio
import requests
import edge_tts
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

GROQ_KEY = os.environ["GROQ_API_KEY"]
PEXELS_KEY = os.environ["PEXELS_API_KEY"]


def call_gemini(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(url, headers=headers, json=data, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate_content():
    prompt = (
        "اكتب قصة عربية مشوقة مناسبة للسرد الصوتي في فيديو يوتيوب مدته من 2 إلى 3 دقائق "
        "(حوالي 350 إلى 500 كلمة تقريبًا). يجب أن تكون قصة كاملة الأحداث بحبكة واضحة وبداية ووسط "
        "ونهاية، بأسلوب سردي جذاب.\n\n"
        "أعطني أيضًا:\n"
        "- عنوان جذاب للفيديو (أقل من 90 حرف)\n"
        "- وصف قصير للفيديو (3-4 جمل)\n"
        "- 8 كلمات مفتاحية بالإنجليزية تصف مشاهد بصرية مناسبة لهذه القصة (مثل: forest, night city, ocean waves)\n\n"
        "أعد الإجابة بصيغة JSON فقط بدون أي نص إضافي أو علامات markdown، بالشكل التالي:\n"
        '{"story": "...", "title": "...", "description": "...", "visual_keywords": ["...", "..."]}'
    )
    raw = call_gemini(prompt).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


content = generate_content()
story_text = content["story"]
video_title = content["title"]
description = content["description"]
keywords = content["visual_keywords"]

print("تم توليد القصة والعنوان:")
print(video_title)


async def make_audio():
    communicate = edge_tts.Communicate(story_text, "ar-EG-ShakirNeural")
    await communicate.save("story.mp3")

asyncio.run(make_audio())

audio_clip = AudioFileClip("story.mp3")
target_duration = audio_clip.duration
print(f"مدة الصوت: {target_duration:.1f} ثانية")


def fetch_pexels_clips(keywords, need_duration):
    headers = {"Authorization": PEXELS_KEY}
    clips = []
    total = 0.0
    attempt = 0
    while total < need_duration and attempt < len(keywords) * 4:
        kw = keywords[attempt % len(keywords)]
        attempt += 1
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": kw, "orientation": "portrait", "per_page": 5, "size": "medium"},
                timeout=30,
            )
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            if not videos:
                continue
            video = videos[attempt % len(videos)]
            files = [f for f in video["video_files"] if f.get("width")]
            files.sort(key=lambda f: f["width"])
            chosen = next((f for f in files if 480 <= f["width"] <= 1080), files[-1])
            fname = f"clip_{len(clips)}.mp4"
            r = requests.get(chosen["link"], timeout=60)
            with open(fname, "wb") as f:
                f.write(r.content)
            c = VideoFileClip(fname)
            total += c.duration
            c.close()
            clips.append(fname)
        except Exception as e:
            print(f"تخطي مقطع بسبب: {e}")
            continue
    return clips


clip_files = fetch_pexels_clips(keywords, target_duration)
print(f"تم تحميل {len(clip_files)} مقطع فيديو")

video_clips = [VideoFileClip(f) for f in clip_files]
final_video = concatenate_videoclips(video_clips, method="compose")

if final_video.duration < target_duration:
    loops_needed = math.ceil(target_duration / final_video.duration)
    final_video = concatenate_videoclips([final_video] * loops_needed, method="compose")

final_video = final_video.subclipped(0, target_duration)
final_video = final_video.resized(height=1280)
final_video = final_video.with_audio(audio_clip)

print("بعمل الفيديو النهائي...")
final_video.write_videofile("story.mp4", fps=25, codec="libx264", audio_codec="aac")
print("الفيديو جاهز")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
creds = Credentials.from_authorized_user_info(
    json.loads(os.environ["YT_TOKEN_JSON"]), SCOPES
)
if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())

youtube = build("youtube", "v3", credentials=creds)

hashtags = "#" + " #".join(["قصص", "قصة", "قصص_عربية", "story", "shorts"])
full_description = f"{description}\n\n{hashtags}"

request = youtube.videos().insert(
    part="snippet,status",
    body={
        "snippet": {
            "title": video_title[:100],
            "description": full_description,
            "tags": keywords,
            "categoryId": "24",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    },
    media_body=MediaFileUpload("story.mp4"),
)
response = request.execute()
print(f"تم رفع الفيديو: https://youtube.com/watch?v={response['id']}")
