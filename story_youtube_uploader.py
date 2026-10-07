import os
import json
import math
import time
import re
import random
import subprocess
import asyncio
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

import edge_tts
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

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

# سجل القصص المنشورة (عشان البوت ميكررش قصة)
HISTORY_PATH = Path(os.environ.get("HISTORY_PATH", "content/published_stories.json"))
HISTORY_AVOID_LAST = 80

# طول القصة بالكلمات (2500 كلمة تقريبًا = 15-17 دقيقة صوت)
STORY_TARGET_WORDS = int(os.environ.get("STORY_TARGET_WORDS", "2500"))
CTA_AFTER_SECONDS = 20

# الموديل الأساسي + بدائل لو الموديل اتشال من جوجل (404)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash").split(",")
    if m.strip()
]
GEMINI_MODELS = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]

STORY_CATEGORIES = [
    "حوادث ومغامرات تاريخية",
    "قضايا جنائية شهيرة تم حلها",
    "قصص نجاة حقيقية",
    "اكتشافات علمية غيّرت العالم",
    "كوارث طبيعية أو صناعية وما تعلمناه منها",
    "ألغاز تاريخية موثقة",
    "رحلات استكشاف ومهام فضائية",
    "قصص أشخاص غيّروا مجرى التاريخ",
]

DEFAULT_KEYWORDS = [
    "mystery", "night", "dramatic lighting", "cinematic",
    "storytelling", "shadows", "suspense", "city",
]

AI_NOTE = "ملاحظة: القصة مبنية على أحداث حقيقية موثقة، والسرد مُنتَج بمساعدة الذكاء الاصطناعي."


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------
# سجل القصص المنشورة
# ----------------------------------------------------------------------
def load_history():
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ تعذّر قراءة سجل القصص ({e})، هنكمل بسجل فارغ")
        return []


def add_history_entry(entry):
    history = load_history()
    history.append(entry)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_json(HISTORY_PATH, history)


# ----------------------------------------------------------------------
# Gemini
# ----------------------------------------------------------------------
def _extract_text(payload):
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini لم يرجع أي نتيجة: {payload.get('promptFeedback')}")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise RuntimeError(f"رد Gemini فارغ (finishReason={candidate.get('finishReason')})")
    if candidate.get("finishReason") == "MAX_TOKENS":
        print("⚠️ رد Gemini اتقطع لأنه وصل للحد الأقصى من التوكنز")
    return text.strip()


def call_gemini(prompt, max_retries=4, base_delay=5, max_output_tokens=8192):
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1.2,
            "topP": 0.95,
            "maxOutputTokens": max_output_tokens,
        },
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY}
    last_error = None

    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(1, max_retries + 1):
            resp = None
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=180)
                resp.raise_for_status()
                return _extract_text(resp.json())
            except requests.exceptions.HTTPError as e:
                last_error = e
                status = resp.status_code if resp is not None else None
                if status == 404:
                    print(f"⚠️ الموديل {model} مش متاح (404)، هجرّب الموديل التالي...")
                    break
                if status in (503, 500, 429):
                    if attempt < max_retries:
                        delay = base_delay * attempt
                        print(f"⚠️ Gemini error {status}, إعادة محاولة بعد {delay} ثانية (محاولة {attempt}/{max_retries})...")
                        time.sleep(delay)
                        continue
                    print(f"⚠️ الموديل {model} مشغول (خطأ {status})، هجرّب الموديل التالي...")
                    break
                raise
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < max_retries:
                    delay = base_delay * attempt
                    print(f"⚠️ خطأ في الشبكة: {e}, إعادة محاولة بعد {delay} ثانية (محاولة {attempt}/{max_retries})...")
                    time.sleep(delay)
                    continue
                raise

    raise RuntimeError(f"كل موديلات Gemini فشلت: {GEMINI_MODELS} — آخر خطأ: {last_error}")


def parse_json_loose(raw):
    """يحوّل رد Gemini إلى JSON حتى لو فيه علامات markdown أو كلام زيادة."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start:end + 1])
        raise


# ----------------------------------------------------------------------
# اختيار الموضوع وكتابة القصة
# ----------------------------------------------------------------------
def pick_topic(history, max_attempts=3):
    avoid = [(h.get("topic") or h.get("title") or "").strip() for h in history[-HISTORY_AVOID_LAST:]]
    avoid = [a for a in avoid if a]
    avoid_text = "\n".join(f"- {a}" for a in avoid) if avoid else "لا يوجد"
    category = random.choice(STORY_CATEGORIES)

    prompt = (
        "أنت محرر قناة يوتيوب عربية اسمها «قصص واقعية» تروي أحداثًا حقيقية موثقة بأسلوب سردي مشوق.\n\n"
        f"اقترح موضوعًا واحدًا جديدًا لقصة واقعية من فئة: {category}.\n"
        "الشروط:\n"
        "- حدث أو قضية حقيقية موثقة في مصادر معروفة (أرشيف صحفي، تقارير رسمية، موسوعات).\n"
        "- ليس خرافة ولا إشاعة ولا نظرية مؤامرة، ولا تخترع أحداثًا أو أشخاصًا.\n"
        "- مناسب للمشاهد العربي، بلا مشاهد عنف مفصلة ولا محتوى جنسي.\n"
        "- لا يكرر ولا يشبه أي موضوع من هذه القائمة المنشورة سابقًا:\n"
        f"{avoid_text}\n\n"
        "أعد الإجابة بصيغة JSON فقط بدون أي نص إضافي أو علامات markdown، بالشكل التالي:\n"
        '{"topic": "وصف الموضوع في جملة واحدة", "key_facts": ["حقيقة موثقة", "..."]}\n'
        "اذكر في key_facts من 5 إلى 8 حقائق أساسية مؤكدة ومشهورة فقط (أسماء وتواريخ وأرقام معروفة)."
    )

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            raw = call_gemini(prompt, max_output_tokens=4096 * attempt)
            data = parse_json_loose(raw)
            topic = str(data.get("topic", "")).strip()
            if not topic:
                raise ValueError("الموضوع فاضي")
            if topic in avoid:
                raise ValueError(f"الموضوع متكرر: {topic}")
            facts = [str(f).strip() for f in data.get("key_facts", []) if str(f).strip()]
            return {"topic": topic, "category": category, "key_facts": facts}
        except Exception as e:
            last_error = e
            print(f"⚠️ فشل اختيار الموضوع (محاولة {attempt}/{max_attempts}): {e}")
    raise RuntimeError(f"فشل اختيار موضوع القصة: {last_error}")


def clean_narration(text):
    text = re.sub(r"[*#`]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def generate_story(topic_info):
    facts = "\n".join(f"- {f}" for f in topic_info["key_facts"]) or "- اعتمد فقط على ما هو مشهور وموثق."
    minutes = max(1, round(STORY_TARGET_WORDS / 150))
    prompt = (
        f"اكتب نصًا عربيًا أصليًا لسرد صوتي على قناة «قصص واقعية»، موضوعه قصة حقيقية موثقة: {topic_info['topic']}.\n\n"
        f"النقاط المرجعية:\n{facts}\n\n"
        f"المدة المطلوبة تقريبًا {minutes} دقيقة، وبحدود {STORY_TARGET_WORDS} كلمة.\n"
        "التزم بالوقائع المعروفة والموثقة فقط. لا تخترع حوارات أو أسماء أو تواريخ أو أرقامًا. "
        "إذا كان شيء غير مؤكد أو محل خلاف فقل ذلك بوضوح.\n"
        "قسّم السرد إلى: افتتاحية قوية في أول 20 ثانية، سياق زمني، تصاعد الأحداث، لحظة الذروة، "
        "ثم خاتمة تشرح ما نعرفه وما لا نعرفه.\n"
        f"بعد الافتتاحية وليس قبل أول {CTA_AFTER_SECONDS} ثانية، أضف فاصلًا واحدًا قصيرًا وطبيعيًا "
        "يدعو المشاهد للاشتراك ويطرح سؤالًا واحدًا للتعليقات، دون قطع التوتر.\n"
        "في النهاية أضف خاتمة قصيرة تدعو للاشتراك لمتابعة قصص واقعية جديدة، دون مبالغة.\n\n"
        "أخرج متن السرد فقط، بدون Markdown أو JSON أو عناوين تقنية أو إرشادات إخراج."
    )
    return clean_narration(call_gemini(prompt, max_output_tokens=32768))


def generate_metadata(story_text, topic, max_attempts=3):
    prompt = (
        "اقرأ القصة التالية ثم أعطني معلومات عنها:\n\n"
        f"الموضوع: {topic}\n\n"
        f"القصة:\n{story_text[:1500]}...\n\n"
        "أعطني:\n"
        "- عنوان جذاب للفيديو (أقل من 90 حرف) بدون مبالغة أو معلومات غير صحيحة\n"
        "- وصف قصير للفيديو (3-4 جمل)\n"
        "- 8 كلمات مفتاحية بالإنجليزية تصف مشاهد بصرية مناسبة لهذه القصة (مثل: forest, night city, ocean waves)\n\n"
        "أعد الإجابة بصيغة JSON فقط بدون أي نص إضافي أو علامات markdown، بالشكل التالي:\n"
        '{"title": "...", "description": "...", "visual_keywords": ["...", "..."]}'
    )

    last_error = None
    for attempt in range(1, max_attempts + 1):
        # الموديلات الحديثة بتستهلك جزء من التوكنز في التفكير، فبنبدأ بميزانية أكبر
        tokens_budget = 4096 + (attempt - 1) * 2048
        try:
            raw = call_gemini(prompt, max_output_tokens=tokens_budget)
            return parse_json_loose(raw)
        except Exception as e:
            last_error = e
            print(f"⚠️ فشل توليد الـ metadata (محاولة {attempt}/{max_attempts}): {e}")

    # لو كل المحاولات فشلت منوقعش البرنامج: نستخدم الموضوع كعنوان
    print(f"❌ فشلت كل محاولات توليد الـ metadata ({last_error}), هنستخدم قيم افتراضية")
    return {
        "title": topic[:90],
        "description": topic,
        "visual_keywords": DEFAULT_KEYWORDS,
    }


# ----------------------------------------------------------------------
# الصوت (TTS)
# ----------------------------------------------------------------------
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


def _make_audio_xtts(story_text):
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


def _make_audio_fish(story_text):
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


async def _make_audio_edge(story_text):
    communicate = edge_tts.Communicate(story_text, "ar-EG-ShakirNeural")
    await communicate.save("story.mp3")


def make_audio(story_text):
    try:
        if TTS_BACKEND == "xtts":
            _make_audio_xtts(story_text)
        elif TTS_BACKEND == "edge":
            asyncio.run(_make_audio_edge(story_text))
        else:
            _make_audio_fish(story_text)
    except Exception as e:
        if TTS_BACKEND == "xtts":
            print(f"❌ فشل XTTS، سيتم إيقاف التشغيل حتى لا نرفع فيديو بصوت مختلف: {e}")
            raise
        print(f"⚠️ فشل TTS backend={TTS_BACKEND} ({e})، هنستخدم edge-tts كبديل")
        asyncio.run(_make_audio_edge(story_text))


# ----------------------------------------------------------------------
# الفيديو
# ----------------------------------------------------------------------
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


def render_video(clip_files, audio_clip, target_duration):
    try:
        from kaggle_client import render_video_via_kaggle
        kaggle_success = render_video_via_kaggle(
            audio_path="story.mp3",
            clip_files=clip_files,
            target_duration=target_duration,
            output_path="story.mp4",
        )
    except Exception as e:
        print(f"⚠️ تخطي Kaggle بسبب خطأ غير متوقع: {e}")
        kaggle_success = False

    if kaggle_success:
        return

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


# ----------------------------------------------------------------------
# الرفع على يوتيوب
# ----------------------------------------------------------------------
def upload_to_youtube(video_title, description, keywords):
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"]), scopes)
    creds.refresh(Request())
    youtube = build("youtube", "v3", credentials=creds)

    hashtags = "#" + " #".join(["قصص_واقعية", "قصص", "قصة", "قصص_عربية", "story"])
    full_description = f"{description}\n\n{AI_NOTE}\n\n{hashtags}"

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
                "tags": keywords + ["قصص واقعية", "قصص", "قصة"],
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
    return response["id"], privacy_status, scheduled_publish_at


# ----------------------------------------------------------------------
# التشغيل
# ----------------------------------------------------------------------
def main():
    history = load_history()
    print(f"عدد القصص المنشورة سابقًا في السجل: {len(history)}")

    topic_info = pick_topic(history)
    topic = topic_info["topic"]
    print(f"الفئة: {topic_info['category']}")
    print(f"الموضوع: {topic}")

    story_text = generate_story(topic_info)
    word_count = len(story_text.split())
    print(f"عدد كلمات القصة: {word_count}")
    min_words = max(600, STORY_TARGET_WORDS // 3)
    if word_count < min_words:
        raise RuntimeError(
            f"القصة قصيرة جدًا ({word_count} كلمة، المطلوب على الأقل {min_words}) — أوقفنا التشغيل بدل رفع فيديو ناقص"
        )

    meta = generate_metadata(story_text, topic)
    video_title = str(meta.get("title") or topic).strip()
    description = str(meta.get("description") or topic).strip()
    keywords = [str(k).strip() for k in (meta.get("visual_keywords") or []) if str(k).strip()]
    if not keywords:
        keywords = list(DEFAULT_KEYWORDS)
    print(f"العنوان: {video_title}")

    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    story_id = created_at.strftime("%Y%m%d-%H%M%S")

    save_json(
        METADATA_PATH,
        {
            "story_id": story_id,
            "title": video_title,
            "description": description,
            "topic": topic,
            "category": topic_info["category"],
            "tags": keywords,
            "story_word_count": word_count,
            "tts_backend": TTS_BACKEND,
            "created_at": created_at.isoformat(),
        },
    )

    make_audio(story_text)
    audio_clip = AudioFileClip("story.mp3")
    target_duration = audio_clip.duration
    print(f"مدة الصوت: {target_duration:.1f} ثانية")

    clip_files = fetch_pexels_clips(keywords, target_duration)
    print(f"تم تحميل {len(clip_files)} مقطع فيديو")
    if not clip_files:
        raise RuntimeError("لم يتم تحميل أي مقاطع فيديو من Pexels")

    render_video(clip_files, audio_clip, target_duration)

    print("الفيديو جاهز")
    save_json(
        STATE_PATH,
        {
            "status": "rendered",
            "video": "story.mp4",
            "metadata": METADATA_PATH,
            "story_id": story_id,
        },
    )

    video_id, privacy_status, scheduled_publish_at = upload_to_youtube(video_title, description, keywords)

    # نسجل القصة فورًا بعد الرفع عشان متتكررش في التشغيل الجاي
    add_history_entry(
        {
            "story_id": story_id,
            "topic": topic,
            "title": video_title,
            "youtube_video_id": video_id,
            "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
    )

    save_json(
        STATE_PATH,
        {
            "status": "uploaded",
            "youtube_video_id": video_id,
            "video": "story.mp4",
            "metadata": METADATA_PATH,
            "story_id": story_id,
            "privacy_status": privacy_status,
            "scheduled_publish_at": scheduled_publish_at,
        },
    )
    if scheduled_publish_at:
        print(f"تم رفع الفيديو كخاص ومجدول للنشر العام: {scheduled_publish_at}")
    else:
        print(f"تم رفع الفيديو: https://youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()
