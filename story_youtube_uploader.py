import os
import json
import math
import time
import asyncio
import requests
import edge_tts
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

import random

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_KEY = os.environ["PEXELS_API_KEY"]

STORY_THEMES = [
    "قصة رعب خفيف تجري أحداثها في بيت قديم مهجور",
    "قصة غموض وجريمة يحاول فيها البطل حل لغز محير",
    "قصة خيال علمي عن اكتشاف أو اختراع غريب يغيّر حياة البطل",
    "قصة رومانسية مؤثرة بين شخصيتين تفرقهما الظروف",
    "قصة تاريخية مستوحاة من حدث أو حقبة زمنية قديمة",
    "قصة عن صراع إنسان مع الطبيعة أو الحيوانات البرية",
    "قصة عن خيانة صديق مقرب واكتشاف الحقيقة",
    "قصة عن رحلة أو سفر ينتهي بمفاجأة غير متوقعة",
    "قصة عن شخص يواجه قرارًا أخلاقيًا صعبًا يغيّر مصيره",
    "قصة خرافية بها عنصر خارق للطبيعة أو أسطوري",
    "قصة عن انتقام طال انتظاره وتبعاته",
    "قصة عن عائلة تخفي سرًا قديمًا ينكشف فجأة",
]


def call_gemini(prompt, max_retries=4, base_delay=5, max_output_tokens=8192):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    )
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1.2,
            "topP": 0.95,
            "maxOutputTokens": max_output_tokens,
        },
    }
    for attempt in range(1, max_retries + 1):
        resp = None
        try:
            resp = requests.post(
                url, headers={"Content-Type": "application/json"}, json=data, timeout=180
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except requests.exceptions.HTTPError:
            status = resp.status_code if resp is not None else None
            if status in (503, 500, 429) and attempt < max_retries:
                delay = base_delay * attempt
                print(f"⚠️ Gemini error {status}, إعادة محاولة بعد {delay} ثانية (محاولة {attempt}/{max_retries})...")
                time.sleep(delay)
                continue
            raise
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                delay = base_delay * attempt
                print(f"⚠️ خطأ في الشبكة: {e}, إعادة محاولة بعد {delay} ثانية (محاولة {attempt}/{max_retries})...")
                time.sleep(delay)
                continue
            raise


def generate_story(theme):
    prompt = (
        f"اكتب {theme}، مناسبة للسرد الصوتي في فيديو يوتيوب طويل مدته من 10 إلى 15 دقيقة "
        "(حوالي 1800 إلى 2500 كلمة تقريبًا). يجب أن تكون قصة كاملة الأحداث بحبكة متماسكة وغنية "
        "بالتفاصيل والأحداث الفرعية، ببداية تشد الانتباه من أول جملة، ووسط مليء بالتصعيد والتشويق، "
        "ونهاية مُرضية ومؤثرة. اكتب بأسلوب سردي جذاب وغني بالوصف، ومختلف عن القصص التقليدية المكررة.\n\n"
        "اكتب القصة فقط كنص عادي متصل، بدون أي عناوين أو تقديم أو تعليق، وبدون علامات markdown، "
        "وبدون أي صيغة JSON — فقط متن القصة كنص سردي."
    )
    return call_gemini(prompt, max_output_tokens=8192).strip()


def generate_metadata(story_text, max_attempts=3):
    prompt = (
        "اقرأ القصة التالية ثم أعطني معلومات عنها:\n\n"
        f"القصة:\n{story_text[:1500]}...\n\n"
        "أعطني:\n"
        "- عنوان جذاب للفيديو (أقل من 90 حرف)\n"
        "- وصف قصير للفيديو (3-4 جمل)\n"
        "- 8 كلمات مفتاحية بالإنجليزية تصف مشاهد بصرية مناسبة لهذه القصة (مثل: forest, night city, ocean waves)\n\n"
        "أعد الإجابة بصيغة JSON فقط بدون أي نص إضافي أو علامات markdown، بالشكل التالي:\n"
        '{"title": "...", "description": "...", "visual_keywords": ["...", "..."]}'
    )

    last_error = None
    for attempt in range(1, max_attempts + 1):
        # نزود الـ token budget مع كل محاولة فاشلة، لأن القطع بيحصل غالبًا
        # لأن الرد بيتقطع قبل ما يخلص (خصوصًا مع النص العربي اللي بياخد
        # توكنز أكتر من الإنجليزي لنفس عدد الكلمات).
        tokens_budget = 1024 + (attempt - 1) * 1024
        raw = call_gemini(prompt, max_output_tokens=tokens_budget).strip()

        # تنظيف أي markdown fences من البداية والنهاية
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = e
            # محاولة إصلاح: ياخد بس من أول { لحد آخر } موجودة في النص
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start:end + 1])
                except json.JSONDecodeError as e2:
                    last_error = e2
            print(
                f"⚠️ رد Gemini كان JSON غير مكتمل (محاولة {attempt}/{max_attempts}), "
                f"هنعيد المحاولة بـ token budget أكبر..."
            )

    # لو كل المحاولات فشلت، منوقعش البرنامج كله - نرجع قيم افتراضية
    # عشان الفيديو يكمل ويتنشر بعنوان ووصف عام بدل ما الـ run كله يفشل
    print(f"❌ فشلت كل محاولات توليد الـ metadata ({last_error}), هنستخدم قيم افتراضية")
    return {
        "title": "قصة مثيرة ستأخذك في رحلة لا تُنسى",
        "description": "قصة سردية مشوقة من إعداد الذكاء الاصطناعي، استمتع بالمشاهدة.",
        "visual_keywords": [
            "mystery", "night", "forest", "dramatic lighting",
            "cinematic", "storytelling", "shadows", "suspense",
        ],
    }


def generate_content():
    theme = random.choice(STORY_THEMES)
    story_text = generate_story(theme)
    metadata = generate_metadata(story_text)
    return {
        "story": story_text,
        "title": metadata["title"],
        "description": metadata["description"],
        "visual_keywords": metadata["visual_keywords"],
    }


content = generate_content()
story_text = content["story"]
video_title = content["title"]
description = content["description"]
keywords = content["visual_keywords"]

print("تم توليد القصة والعنوان:")
print(video_title)
print(f"عدد كلمات القصة: {len(story_text.split())}")


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
    max_attempts = len(keywords) * 30
    while total < need_duration and attempt < max_attempts:
        kw = keywords[attempt % len(keywords)]
        attempt += 1
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": kw, "orientation": "portrait", "per_page": 15, "size": "medium"},
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

video_clips = [VideoFileClip(f).resized(height=1280) for f in clip_files]
final_video = concatenate_videoclips(video_clips, method="chain")

if final_video.duration < target_duration:
    loops_needed = math.ceil(target_duration / final_video.duration)
    final_video = concatenate_videoclips([final_video] * loops_needed, method="chain")

final_video = final_video.subclipped(0, target_duration)
final_video = final_video.with_audio(audio_clip)

print("بعمل الفيديو النهائي...")
final_video.write_videofile(
    "story.mp4",
    fps=25,
    codec="libx264",
    audio_codec="aac",
    preset="veryfast",
    threads=4,
    ffmpeg_params=["-crf", "23"],
)
print("الفيديو جاهز")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
creds = Credentials.from_authorized_user_info(
    json.loads(os.environ["YT_TOKEN_JSON"]), SCOPES
)
creds.refresh(Request())

youtube = build("youtube", "v3", credentials=creds)

hashtags = "#" + " #".join(["قصص", "قصة", "قصص_عربية", "story"])
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
