import os
import json
import math
import time
import re
import subprocess
import asyncio
import requests
from datetime import datetime, timedelta, timezone
import edge_tts
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from pathlib import Path

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_KEY = os.environ["PEXELS_API_KEY"]
FISH_API_KEY = os.environ.get("FISH_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")
TTS_BACKEND = os.environ.get("TTS_BACKEND", "fish").lower()
VOICE_REFERENCE_PATH = os.environ.get("VOICE_REFERENCE_PATH", "voice_reference.wav")
XTTS_LANGUAGE = os.environ.get("XTTS_LANGUAGE", "ar")
PUBLISH_DELAY_MINUTES = int(os.environ.get("PUBLISH_DELAY_MINUTES", "30"))
METADATA_PATH = "story_metadata.json"
STATE_PATH = "upload_state.json"
SERIES_MANIFEST_PATH = os.environ.get("SERIES_MANIFEST_PATH", "content/series/real_stories.json")
GROWTH_POLICY_PATH = os.environ.get("GROWTH_POLICY_PATH", "content/strategy/growth_policy.json")
EPISODE_SELECTOR = os.environ.get("EPISODE_NUMBER", "1").strip().lower()


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def load_growth_policy():
    return json.loads(Path(GROWTH_POLICY_PATH).read_text(encoding="utf-8"))


def load_episode():
    manifest = json.loads(Path(SERIES_MANIFEST_PATH).read_text(encoding="utf-8"))
    episodes = sorted(manifest["episodes"], key=lambda item: item["episode_number"])
    eligible = [
        item for item in episodes
        if not item.get("published", False)
        and not item.get("disabled", False)
        and item.get("content_type", manifest.get("content_type")) == "verified_real_story"
        and len(item.get("sources", [])) >= 2
        and len({source.get("publisher", "").strip().lower() for source in item.get("sources", [])}) >= 2
        and bool(item.get("verified_facts"))
        and all(source.get("title") and source.get("publisher") and source.get("url", "").startswith("https://")
                for source in item.get("sources", []))
    ]
    if EPISODE_SELECTOR == "next":
        episode = next((item for item in eligible), None)
        if episode is None:
            raise ValueError(
                "لا توجد حلقة مؤهلة للنشر: أضف حلقة verified_real_story بمصدرين موثوقين على الأقل "
                "واجعلها غير منشورة وغير معطلة. تم إيقاف الحلقات الخيالية لمنع تقديمها كوقائع."
            )
    else:
        try:
            requested_number = int(EPISODE_SELECTOR)
        except ValueError as exc:
            raise ValueError("EPISODE_NUMBER يجب أن يكون رقم حلقة أو next") from exc
        episode = next((item for item in episodes if item["episode_number"] == requested_number), None)
        if episode is None:
            raise ValueError(f"الحلقة {requested_number} غير موجودة")
        if episode not in eligible:
            raise ValueError(
                f"الحلقة {requested_number} غير مؤهلة: يجب أن تكون قصة حقيقية موثقة بمصدرين على الأقل "
                "وغير منشورة أو معطلة."
            )
    return manifest, episode


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


def generate_story(manifest, episode):
    growth_policy = load_growth_policy()
    sources = "\\n".join(
        f"- {source['title']} — {source['publisher']} — {source['url']}"
        for source in episode["sources"]
    )
    target_words = episode.get("target_words", 1800)
    prompt_parts = [
        f"اكتب نصًا عربيًا أصليًا للحلقة {episode['episode_number']} من سلسلة «{manifest['series_title']}».",
        f"الموضوع: {episode['topic']}",
        f"العنوان التحريري: {episode['title']}",
        f"الافتتاحية: {episode['opening_hook']}",
        "نوع المحتوى: قصة اجتماعية أسرية واقعية موثقة. لا تستخدم إلا الوقائع الواردة في قائمة الوقائع المتحققة والمصادر أدناه.",
        "الوقائع المتحققة التي يجب الالتزام بها:\\n" + "\\n".join("- " + fact for fact in episode.get("verified_facts", [])),
        "ممنوع اختلاق حوار أو مشاهد خاصة أو دوافع أو أسماء أو تواريخ أو أرقام أو نتائج.",
        "إذا تضمنت القضية جريمة أو عنفًا، فهذه حلقة اجتماعية وثائقية: امتنع تمامًا عن أي وصف دموي أو تفصيلي للعنف؛ ركز على السياق الصحفي والقضائي والتاريخي فقط.",
        "لا تنقل صياغة المصادر حرفيًا؛ اكتب شرحًا وسردًا أصليًا مع ذكر المصدر في الوصف.",
        "إذا تعارضت المصادر أو لم تثبت معلومة، وضّح عدم اليقين ولا تعرضها كحقيقة.",
        "احمِ خصوصية الأشخاص غير المعروفين؛ لا تضف بيانات تعريفية أو تفاصيل شخصية غير منشورة وضرورية.",
        f"المصادر المعتمدة:\\n{sources}",
        f"الطول المستهدف نحو {target_words} كلمة، والسرد باللهجة المصرية البيضاء.",
        f"ضع دعوة واحدة طبيعية بعد أول {growth_policy['cta']['never_before_core_hook_seconds']} ثانية، ثم خاتمة موجزة.",
        "أخرج متن السرد فقط دون Markdown أو JSON أو عناوين تقنية."
    ]
    return call_gemini("\\n\\n".join(prompt_parts), max_output_tokens=12288).strip()


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
    manifest, episode = load_episode()
    story_text = generate_story(manifest, episode)
    return {
        "manifest": manifest,
        "episode": episode,
        "story": story_text,
        "title": episode["title"],
        "description": episode["description"],
        "visual_keywords": episode["visual_keywords"],
    }


content = generate_content()
growth_policy = load_growth_policy()
manifest = content["manifest"]
episode = content["episode"]
story_text = content["story"]
video_title = content["title"]
description = content["description"]

def generate_teaser_script(manifest, episode, story_text):
    """Create an original short-form teaser from the selected episode, not a raw crop."""
    prompt = (
        "اكتب نص تعليق صوتي عربي مصري طبيعي لريلز ترويجي مدته 30 إلى 50 ثانية "
        "عن القصة الموثقة التالية. افتح بسؤال أو مفارقة قوية خلال أول ثانيتين، "
        "ثم اذكر 2-3 تفاصيل موثقة من النص، وصعّد التشويق دون كشف الخاتمة. "
        "اختم بدعوة واضحة: شاهد القصة الكاملة على قناة قصص واقعيه. "
        "لا تخترع أي معلومة أو حوار أو نتيجة، ولا تكتب عنوانًا أو تعليمات تصوير أو روابط. "
        "أخرج التعليق الصوتي فقط، في حدود 75-105 كلمات.\\n"
        f"عنوان الحلقة: {episode['title']}\\n"
        f"الافتتاحية المعتمدة: {episode['opening_hook']}\\n"
        f"المصادر: " + "; ".join(s['title'] + " (" + s['publisher'] + ")" for s in episode['sources']) + "\\n"
        f"نص القصة للاستناد إلى وقائعه فقط:\\n{story_text[:10000]}"
    )
    teaser = call_gemini(prompt, max_output_tokens=1200).strip()
    word_count = len(teaser.split())

    # Gemini may occasionally return a short answer despite the requested length.
    # Retry once with an explicit minimum; do not publish a weak teaser.
    if word_count < 35:
        retry_prompt = (
            prompt
            + "\\nمهم جدًا: إجابتك السابقة كانت قصيرة أكثر من اللازم. أعد كتابة النص كاملًا "
            + "في 80 إلى 100 كلمة عربية فعلية، مع 2-3 تفاصيل موثقة ونداء واضح لمشاهدة الحلقة الكاملة. "
            + "أخرج التعليق الصوتي فقط، دون مقدمة أو شرح."
        )
        teaser = call_gemini(retry_prompt, max_output_tokens=1600).strip()
        word_count = len(teaser.split())

    if word_count < 35 or word_count > 110:
        # Never pass a full episode script to the Shorts renderer. Build a compact,
        # grounded teaser from the approved hook and story, capped at 100 words.
        sentences = re.split(r"(?<=[.!؟?])\\s+", story_text.strip())
        selected = [episode["opening_hook"].strip()]
        count = len(selected[0].split())
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            n = len(sentence.split())
            if count + n > 88:
                continue
            selected.append(sentence)
            count += n
            if count >= 72:
                break
        teaser = " ".join(selected) + " شاهد القصة كاملة على قناة قصص واقعيه."
        words = teaser.split()
        if len(words) > 100:
            teaser = " ".join(words[:94]) + " شاهد القصة كاملة على قناة قصص واقعيه."
        word_count = len(teaser.split())
    if word_count < 35 or word_count > 110:
        raise ValueError(
            f"تعذر إنشاء نص ريلز صالح حتى بالصياغة الاحتياطية ({word_count} كلمة)."
        )
    print(f"تم إنشاء نص الريلز التشويقي ({word_count} كلمة).")
    return teaser


keywords = content["visual_keywords"]
teaser_script = generate_teaser_script(manifest, episode, story_text)

print(f"تم اختيار السلسلة: {manifest['series_title']}")
print(f"الحلقة {episode['episode_number']}: {video_title}")
print(f"عدد كلمات القصة: {len(story_text.split())}")
sources_text = "\n".join(f"{source['title']} — {source['publisher']}: {source['url']}" for source in episode['sources'])
save_json(
    METADATA_PATH,
    {
        "series_id": manifest["series_id"],
        "series_title": manifest["series_title"],
        "episode_id": episode["episode_id"],
        "episode_number": episode["episode_number"],
        "title": video_title,
        "short_title": episode.get("short_title", video_title),
        "description": description,
        "tags": keywords,
        "story_word_count": len(story_text.split()),
        "target_duration_minutes": manifest["target_duration_minutes"],
        "playlist_title": manifest["playlist_title"],
        "thumbnail_text": episode["thumbnail_text"],
        "opening_hook": episode["opening_hook"],
        "teaser_script": teaser_script,
        "cta_policy": growth_policy["cta"],
        "tts_backend": TTS_BACKEND,
        "sources": episode["sources"],
    },
)


def _split_text_for_tts(text, max_chars=1500):
    """Splits long text into chunks at sentence boundaries so it stays under
    typical TTS API length limits, without cutting words/sentences mid-way."""
    sentences = re.split(r"(?<=[.!؟?\n])\s+", text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = s
        else:
            current = f"{current} {s}".strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks


FISH_TTS_URL = "https://api.fish.audio/v1/tts"
FISH_MODEL = "s2.1-pro-free"


def _make_audio_xtts():
    """Generate Arabic speech locally by cloning the user's reference voice."""
    if not Path(VOICE_REFERENCE_PATH).exists():
        raise FileNotFoundError(f"VOICE_REFERENCE_PATH غير موجود: {VOICE_REFERENCE_PATH}")
    try:
        from TTS.api import TTS
    except ImportError as exc:
        raise RuntimeError("ثبّت coqui-tts لاستخدام XTTS") from exc

    print("🎙️ توليد الصوت محليًا عبر Coqui XTTS-v2...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)
    # XTTS-v2 has a hard limit of 400 tokens; keep Arabic chunks well below it.
    chunks = _split_text_for_tts(story_text, max_chars=350)
    chunk_files = []
    for i, chunk in enumerate(chunks):
        chunk_path = f"xtts_chunk_{i:03d}.wav"
        tts.tts_to_file(
            text=chunk,
            file_path=chunk_path,
            speaker_wav=VOICE_REFERENCE_PATH,
            language=XTTS_LANGUAGE,
            split_sentences=False,
        )
        chunk_files.append(chunk_path)
        print(f"   ✅ XTTS جزء {i + 1}/{len(chunks)}")

    list_path = "xtts_chunks.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for cf in chunk_files:
            f.write(f"file '{cf}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-ar", "24000", "-ac", "1", "story.mp3"],
        check=True, capture_output=True,
    )
    for cf in chunk_files:
        os.remove(cf)
    os.remove(list_path)


def _make_audio_fish():
    """Generate story.mp3 using Fish Audio REST API (voice cloning via
    reference_id = صوتك المستنسخ). Splits long text into chunks (API length
    limits), synthesizes each, then concatenates them with ffmpeg. Raises on
    any failure so the caller can fall back to edge-tts."""
    if not FISH_API_KEY:
        raise RuntimeError("FISH_API_KEY غير موجود")
    if not FISH_VOICE_ID:
        raise RuntimeError("FISH_VOICE_ID غير موجود")

    headers = {
        "Authorization": f"Bearer {FISH_API_KEY}",
        "Content-Type": "application/json",
        "model": FISH_MODEL,
    }

    chunks = _split_text_for_tts(story_text)
    print(f"🐟 توليد الصوت عبر Fish Audio ({len(chunks)} جزء)...")

    chunk_files = []
    for i, chunk in enumerate(chunks):
        payload = {
            "text": chunk,
            "reference_id": FISH_VOICE_ID,
            "format": "mp3",
        }
        resp = requests.post(FISH_TTS_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()

        chunk_path = f"fish_chunk_{i:03d}.mp3"
        with open(chunk_path, "wb") as f:
            f.write(resp.content)
        chunk_files.append(chunk_path)
        print(f"   ✅ جزء {i + 1}/{len(chunks)}")

    if len(chunk_files) == 1:
        os.replace(chunk_files[0], "story.mp3")
        return

    list_path = "fish_chunks.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for cf in chunk_files:
            f.write(f"file '{cf}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c", "copy", "story.mp3"],
        check=True, capture_output=True,
    )
    for cf in chunk_files:
        os.remove(cf)
    os.remove(list_path)


async def _make_audio_edge():
    communicate = edge_tts.Communicate(story_text, "ar-EG-ShakirNeural")
    await communicate.save("story.mp3")


try:
    if TTS_BACKEND == "xtts":
        _make_audio_xtts()
    elif TTS_BACKEND == "edge":
        asyncio.run(_make_audio_edge())
    else:
        _make_audio_fish()
except Exception as e:
    if TTS_BACKEND == "xtts":
        print(f"❌ فشل XTTS، سيتم إيقاف التشغيل حتى لا نرفع فيديو بصوت مختلف: {e}")
        raise
    print(f"⚠️ فشل TTS backend={TTS_BACKEND} ({e})، هنستخدم edge-tts كبديل")
    asyncio.run(_make_audio_edge())

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
                params={"query": kw, "orientation": "landscape", "per_page": 15, "size": "medium"},
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

video_clips_paths = clip_files

try:
    from kaggle_client import render_video_via_kaggle
    kaggle_success = render_video_via_kaggle(
        audio_path="story.mp3",
        clip_files=video_clips_paths,
        target_duration=target_duration,
        output_path="story.mp4",
    )
except Exception as e:
    print(f"⚠️ تخطي Kaggle بسبب خطأ غير متوقع: {e}")
    kaggle_success = False

if not kaggle_success:
    print("↩️ هنكمل الرندر محليًا (Kaggle مش متاح أو فشل)...")
    video_clips = [VideoFileClip(f).resized(width=1280) for f in clip_files]
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
save_json(
    STATE_PATH,
    {
        "status": "rendered",
        "video": "story.mp4",
        "metadata": METADATA_PATH,
        "series_id": manifest["series_id"],
        "episode_id": episode["episode_id"],
        "episode_number": episode["episode_number"],
    },
)

if os.environ.get("ALLOW_UNREVIEWED_PUBLISH", "false").lower() != "true":
    raise RuntimeError(
        "تم إيقاف الرفع التلقائي: راجع النص والفيديو والمصادر وحقوق المواد، "
        "ثم فعّل ALLOW_UNREVIEWED_PUBLISH=true يدويًا بعد الموافقة."
    )

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
creds = Credentials.from_authorized_user_info(
    json.loads(os.environ["YT_TOKEN_JSON"]), SCOPES
)
creds.refresh(Request())

youtube = build("youtube", "v3", credentials=creds)

hashtags = "#" + " #".join(["قصص", "قصة", "قصص_عربية", "story"])
full_description = f"{description}\n\nالمصادر:\n{sources_text}\n\nالحلقة {episode['episode_number']} من سلسلة: {manifest['series_title']}\n\nشاهد الحلقة التالية من قائمة التشغيل: {manifest['playlist_title']}\n\n{hashtags}"

scheduled_publish_at = None
privacy_status = "public"
if PUBLISH_DELAY_MINUTES > 0:
    scheduled_publish_at = (
        datetime.now(timezone.utc) + timedelta(minutes=PUBLISH_DELAY_MINUTES)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    privacy_status = "private"

request = youtube.videos().insert(
    part="snippet,status",
    body={
        "snippet": {
            "title": video_title[:100],
            "description": full_description,
            "tags": keywords,
            "categoryId": "24",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            **({"publishAt": scheduled_publish_at} if scheduled_publish_at else {}),
        },
    },
    media_body=MediaFileUpload("story.mp4"),
)
response = request.execute()
video_id = response["id"]
episode["published"] = True
episode["youtube_video_id"] = video_id
episode["published_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
save_json(SERIES_MANIFEST_PATH, manifest)
save_json(
    STATE_PATH,
    {
        "status": "uploaded",
        "youtube_video_id": video_id,
        "video": "story.mp4",
        "metadata": METADATA_PATH,
        "series_id": manifest["series_id"],
        "episode_id": episode["episode_id"],
        "episode_number": episode["episode_number"],
        "privacy_status": privacy_status,
        "scheduled_publish_at": scheduled_publish_at,
    },
)
if scheduled_publish_at:
    print(f"تم رفع الفيديو كخاص ومجدول للنشر العام: {scheduled_publish_at}")
else:
    print(f"تم رفع الفيديو: https://youtube.com/watch?v={video_id}")
