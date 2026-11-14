#!/usr/bin/env python3
"""Free-tier educational Shorts factory. One idea -> Arabic voice -> 9:16 MP4."""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
IDEAS_FILE = ROOT / "ideas.csv"
USED_FILE = ROOT / "used.txt"
PROMPT_FILE = ROOT / "prompts" / "system_prompt.txt"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / ".work"
WIDTH, HEIGHT, FPS, TARGET_SECONDS = 1080, 1920, 30, 45
FISH_API_KEY = os.getenv("FISH_API_KEY", "").strip()
FISH_VOICE_ID = os.getenv("FISH_VOICE_ID", "").strip()
FISH_TTS_URL = "https://api.fish.audio/v1/tts"
FISH_MODEL = "s2.1-pro-free"
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
IMAGE_BASE = "https://gen.pollinations.ai/image/"
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "").strip()
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "kombo-city-factory/1.0"})


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def require_tools() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError("أدوات ناقصة: " + ", ".join(missing) + ". ثبّت FFmpeg وأعد التشغيل.")


def load_used() -> set[str]:
    if not USED_FILE.exists():
        return set()
    return {line.strip() for line in USED_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")}


def choose_idea() -> dict:
    with IDEAS_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    used = load_used()
    available = [r for r in rows if r.get("id") and r["id"] not in used and r.get("status", "unused") != "used"]
    if not available:
        raise RuntimeError("انتهت الأفكار المتاحة. أضف أفكارًا جديدة إلى ideas.csv.")
    return sorted(available, key=lambda r: int(r["id"]))[0]


def gemini_json(idea: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY غير موجود في GitHub Secrets.")
    template = PROMPT_FILE.read_text(encoding="utf-8")
    prompt = template.replace("{idea}", idea)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.75}
    }
    last_error = None
    for attempt in range(4):
        try:
            response = SESSION.post(url, params={"key": api_key}, json=payload, timeout=90)
            if response.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:300]}")
            response.raise_for_status()
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            text = re.sub(r"^\s*```(?:json)?|\s*```\s*$", "", text, flags=re.I)
            result = json.loads(text)
            required = ("script", "image1", "image2", "image3", "image4", "image5", "image6", "title", "caption", "srt_parts")
            if any(not result.get(k) for k in required) or len(result["srt_parts"]) != 6:
                raise ValueError("Gemini returned incomplete JSON fields.")
            words = result["script"].split()
            if not 65 <= len(words) <= 115:
                raise ValueError(f"طول النص غير مناسب: {len(words)} كلمة (المطلوب 65–115).")
            return result
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"تعذر توليد السيناريو بعد المحاولات: {last_error}")


def generate_image(prompt: str, destination: Path, scene: int) -> None:
    """Generate premium cinematic 3D frames; fail closed instead of publishing primitive placeholders."""
    palette = (
        "ONE SINGLE FULL-FRAME CINEMATIC STILL, one continuous camera shot, vertical 9:16 composition. "
        "This is ONE image for ONE moment in a film, NOT a storyboard, NOT a contact sheet, NOT a collage. "
        "No split screen, no panels, no grids, no triptych, no stacked frames, no repeated subject, no duplicated people. "
        "High-end cinematic 3D animated feature film still, art-directed professional studio quality, "
        "physically based rendering, detailed realistic materials, sophisticated global illumination, "
        "volumetric key light and rim light, atmospheric depth, cinematic color grading, "
        "deep midnight navy, electric cyan and restrained warm gold palette, "
        "visually rich but uncluttered composition, no text, no letters, no typography, no logos, no watermark. "
    )
    host_identity = (
        "Show EXACTLY ONE presenter, appearing ONCE in the entire image. "
        "One head, one face, one torso, one pair of arms, one body. "
        "Young adult male cartoon presenter, warm approachable face, expressive brown eyes, "
        "thick dark wavy hair with a defined silhouette, thin round glasses, "
        "navy tailored hoodie with one small cyan geometric chest mark. "
        "Keep this same character design across separate generated images, but NEVER show multiple copies "
        "or multiple poses of him inside this single image. Premium feature-animation character sculpt, "
        "detailed skin shading, expressive natural hand gesture. "
    )
    if scene in (1, 3, 5):
        fixed = palette + host_identity + (
            "Single-subject presenter portrait, medium shot from waist or chest up, "
            "one clear readable silhouette centered in one uninterrupted studio environment. "
            "No screens, mirrors, posters, background people, picture-in-picture, or character portraits. "
            "Use a distinct camera angle or gesture for this shot while keeping only one presenter visible. "
        )
    else:
        fixed = palette + (
            "CINEMATIC EXPLANATORY CUTAWAY. Absolutely no people, no presenter, no faces, no characters, "
            "no human silhouettes, and no reflections of people. Show only the actual subject or mechanism "
            "as one hero object in one uninterrupted environment, with physically plausible detail, "
            "layered depth, dramatic macro or wide lens composition. "
        )
    full_prompt = fixed + prompt + (
        " STRICT NEGATIVE COMPOSITION RULES: no collage, no triptych, no storyboard, no comic panels, "
        "no tiled layout, no vertical or horizontal strips, no repeated character, no cloned subject, "
        "no before-and-after layout, no multiple views of the same person, no inset images. "
        "Avoid flat vector art, simple geometric icons, childish clipart, crude drawings, generic robot mascots, "
        "flat lighting, plastic low-detail faces, duplicated limbs, distorted hands, illegible text."
    )
    if not POLLINATIONS_API_KEY:
        raise RuntimeError(
            "POLLINATIONS_API_KEY غير مضبوط في GitHub Actions Secrets. "
            "مزود الصور الحالي يتطلب مفتاحًا سريًا ورصيدًا متاحًا؛ لم نعد نستخدم الرابط القديم."
        )
    url = IMAGE_BASE + quote(full_prompt, safe="") + "?model=zimage&width=1024&height=1792"
    headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}
    last_error = None
    for attempt in range(3):
        try:
            response = SESSION.get(url, headers=headers, timeout=150)
            if response.status_code == 402:
                raise RuntimeError(
                    "Pollinations HTTP 402: رصيد الحساب أو ميزانية المفتاح غير كافية. "
                    "تحقق من الرصيد وحدود المفتاح لدى المزود؛ لن يعالج تكرار المحاولة هذه المشكلة."
                )
            if response.status_code in (401, 403):
                raise RuntimeError(
                    f"Pollinations HTTP {response.status_code}: مفتاح API غير صالح أو لا يملك صلاحية توليد الصور."
                )
            response.raise_for_status()
            if not response.headers.get("content-type", "").startswith("image/") or len(response.content) < 25_000:
                raise ValueError("Image provider returned a low-quality or invalid image payload.")
            destination.write_bytes(response.content)
            with Image.open(destination) as image_file:
                image_file.verify()
            # The current image endpoint may ignore requested dimensions and return 580x1015.
            # Accept a valid portrait master, then upscale once with a high-quality resampler.
            with Image.open(destination) as image_file:
                image_file = image_file.convert("RGB")
                if image_file.width < 512 or image_file.height < 900:
                    raise ValueError(f"Image resolution too low even for safe upscale: {image_file.width}x{image_file.height}")
                ratio = image_file.width / image_file.height
                if not 0.52 <= ratio <= 0.62:
                    raise ValueError(f"Image is not portrait 9:16: {image_file.width}x{image_file.height}")
                image_file = image_file.resize((1080, 1920), Image.Resampling.LANCZOS)
                image_file = image_file.filter(ImageFilter.UnsharpMask(radius=1.4, percent=115, threshold=3))
                image_file.save(destination, format="JPEG", quality=94, optimize=True)
            print(f"Scene {scene}: accepted portrait frame and normalized to 1080x1920.")
            return
        except Exception as exc:
            last_error = exc
            if attempt < 2 and not (isinstance(exc, RuntimeError) and ("HTTP 402" in str(exc) or "HTTP 401" in str(exc) or "HTTP 403" in str(exc))):
                time.sleep(4 * (attempt + 1))
            elif isinstance(exc, RuntimeError) and ("HTTP 402" in str(exc) or "HTTP 401" in str(exc) or "HTTP 403" in str(exc)):
                break
    raise RuntimeError(
        f"تعذر إنتاج مشهد سينمائي صالح رقم {scene}: {last_error}. "
        "أوقفنا الإنتاج بدل استخدام رسمة احتياطية بدائية أو نشر فيديو ضعيف."
    )


def make_tts(text: str, output: Path) -> None:
    """Generate narration with the configured Fish Audio cloned voice; never silently fall back."""
    if not FISH_API_KEY:
        raise RuntimeError("FISH_API_KEY غير مضبوط في GitHub Secrets.")
    if not FISH_VOICE_ID:
        raise RuntimeError("FISH_VOICE_ID غير مضبوط في GitHub Secrets.")

    chunks = []
    sentences = re.split(r"(?<=[.!؟?])\s+|\n+", text.strip())
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 > 1400 and current:
            chunks.append(current)
            current = sentence
        else:
            current = (current + " " + sentence).strip()
    if current:
        chunks.append(current)
    if not chunks:
        raise ValueError("نص التعليق الصوتي فارغ.")

    headers = {
        "Authorization": f"Bearer {FISH_API_KEY}",
        "Content-Type": "application/json",
        "model": FISH_MODEL,
    }
    generated = []
    try:
        for index, chunk in enumerate(chunks, start=1):
            response = SESSION.post(
                FISH_TTS_URL, headers=headers,
                json={"text": chunk, "reference_id": FISH_VOICE_ID, "format": "mp3"},
                timeout=180,
            )
            response.raise_for_status()
            part = WORK_DIR / f"fish_voice_{index:03d}.mp3"
            part.write_bytes(response.content)
            if part.stat().st_size < 1000:
                raise RuntimeError(f"Fish Audio returned invalid audio chunk {index}.")
            generated.append(part)
            print(f"Fish Audio: الجزء {index}/{len(chunks)}")
        if len(generated) == 1:
            shutil.copy2(generated[0], output)
        else:
            concat = WORK_DIR / "fish_voice_concat.txt"
            concat.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in generated), encoding="utf-8")
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                 "-c:a", "libmp3lame", "-q:a", "2", str(output)])
        if not output.exists() or output.stat().st_size < 1000:
            raise RuntimeError("تعذر إنشاء ملف الصوت النهائي من Fish Audio.")
    finally:
        for part in generated:
            part.unlink(missing_ok=True)
        (WORK_DIR / "fish_voice_concat.txt").unlink(missing_ok=True)


def media_duration(path: Path) -> float:
    result = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                  "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(result.stdout.strip())


def split_script(script: str, parts: list[str]) -> list[str]:
    cleaned = [re.sub(r"\s+", " ", str(p)).strip() for p in parts]
    if len(cleaned) == 6 and all(cleaned):
        return cleaned
    words = script.split()
    return [" ".join(words[round(i*len(words)/6):round((i+1)*len(words)/6)]) for i in range(6)]


def srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def create_captions(script: str, parts: list[str], duration: float, output: Path) -> None:
    chunks = split_script(script, parts)
    lines = []
    count = len(chunks)
    for i, caption in enumerate(chunks):
        start, end = i * duration / count, (i + 1) * duration / count
        lines.extend([str(i + 1), f"{srt_time(start)} --> {srt_time(end)}", caption, ""])
    output.write_text("\n".join(lines), encoding="utf-8-sig")


def build_video(images: list[Path], audio: Path, script: str, captions: Path, output: Path) -> None:
    """Render a polished 45-second vertical short with alternating cinematic camera moves."""
    audio_len = media_duration(audio)
    if audio_len < 20:
        raise RuntimeError(f"الصوت أقصر من المتوقع: {audio_len:.1f} ثانية.")
    tempo = audio_len / TARGET_SECONDS
    if not 0.72 <= tempo <= 1.35:
        raise RuntimeError(f"مدة التعليق {audio_len:.1f}s بعيدة عن 45s؛ عدّل طول النص بدل قص الكلام.")
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    scene_files = []
    fade = 0.35
    scene_count = len(images)
    if scene_count < 6:
        raise RuntimeError("المطلوب 6 مشاهد سينمائية على الأقل.")
    scene_duration = (TARGET_SECONDS + (scene_count - 1) * fade) / scene_count
    frames = int(scene_duration * FPS)
    moves = [
        ("min(zoom+0.00070,1.18)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        ("min(zoom+0.00048,1.12)", "iw/2-(iw/zoom/2)+18*sin(on/18)", "ih/2-(ih/zoom/2)"),
        ("min(zoom+0.00062,1.16)", "iw/2-(iw/zoom/2)-22*sin(on/22)", "ih/2-(ih/zoom/2)+12*sin(on/25)"),
        ("if(lte(zoom,1.10),1.10,max(1.0,zoom-0.00042))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        ("min(zoom+0.00055,1.15)", "iw/2-(iw/zoom/2)+12*sin(on/20)", "ih/2-(ih/zoom/2)-10*sin(on/24)"),
        ("min(zoom+0.00075,1.18)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ]
    for i, image_path in enumerate(images):
        scene = WORK_DIR / f"scene_{i+1}.mp4"
        zoom, xpos, ypos = moves[i]
        vf = (f"scale=1200:2134:force_original_aspect_ratio=increase,crop=1200:2134,"
              f"zoompan=z='{zoom}':x='{xpos}':y='{ypos}':d={frames}:s=1080x1920:fps={FPS},"
              "eq=saturation=1.12:contrast=1.04:brightness=0.01,"
              "vignette=PI/5,setsar=1,format=yuv420p")
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-t", str(scene_duration),
             "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-r", str(FPS), str(scene)])
        scene_files.append(scene)
    # Soft crossfades between scenes instead of hard cuts.
    joined = WORK_DIR / "joined.mp4"
    filter_parts = []
    previous = "[0:v]"
    offset = scene_duration - fade
    for idx in range(1, len(scene_files)):
        out_label = f"[xf{idx}]"
        filter_parts.append(f"{previous}[{idx}:v]xfade=transition=fade:duration={fade}:offset={offset:.3f}{out_label}")
        previous = out_label
        offset += scene_duration - fade
    run(["ffmpeg", "-y", *sum(([ "-i", str(p)] for p in scene_files), []),
         "-filter_complex", ";".join(filter_parts), "-map", previous,
         "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
         "-pix_fmt", "yuv420p", str(joined)])

    subtitle_path = captions.as_posix().replace(":", r"\:")
    font_dir = "/usr/share/fonts/truetype"
    vf_sub = (f"subtitles='{subtitle_path}':fontsdir='{font_dir}':"
              "force_style='FontName=DejaVu Sans,FontSize=20,Bold=1,"
              "PrimaryColour=&H0000D7FF,OutlineColour=&H00101010,BorderStyle=1,"
              "Outline=3,Shadow=1,Alignment=2,MarginV=235'")
    music = ROOT / "assets" / "music.mp3"
    cmd = ["ffmpeg", "-y", "-i", str(joined), "-i", str(audio)]
    if music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        filter_complex = (f"[1:a]atempo={tempo:.5f},apad,atrim=0:{TARGET_SECONDS},volume=1.0[voice];"
                          f"[2:a]volume=0.085,afade=t=in:st=0:d=2,afade=t=out:st=40:d=5[music];"
                          "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]")
    else:
        filter_complex = (f"[1:a]atempo={tempo:.5f},apad,atrim=0:{TARGET_SECONDS},volume=1.0[aout]")
    cmd += ["-filter_complex", filter_complex, "-vf", vf_sub, "-map", "0:v:0", "-map", "[aout]",
            "-t", str(TARGET_SECONDS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-movflags", "+faststart", str(output)]
    run(cmd)
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", str(output)]).stdout)
    video = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    duration = float(probe["format"]["duration"])
    if not video or not audio_stream or int(video["width"]) != WIDTH or int(video["height"]) != HEIGHT:
        raise RuntimeError("فشل فحص مسارات الفيديو أو أبعاد 1080x1920.")
    if abs(duration - TARGET_SECONDS) > 1.0 or output.stat().st_size < 100_000:
        raise RuntimeError(f"فشل فحص الفيديو النهائي: duration={duration:.2f}s, size={output.stat().st_size}.")


def safe_slug(value: str) -> str:
    value = re.sub(r"[^\w\-]+", "_", value, flags=re.UNICODE).strip("_")
    return value[:55] or "kombo"


def mark_used(idea_id: str) -> None:
    used = load_used()
    if idea_id not in used:
        with USED_FILE.open("a", encoding="utf-8") as f:
            f.write(idea_id + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--one", action="store_true", help="Generate one unused idea.")
    args = parser.parse_args()
    require_tools()
    OUTPUT_DIR.mkdir(exist_ok=True)
    WORK_DIR.mkdir(exist_ok=True)
    idea = choose_idea()
    print(f"الفكرة #{idea['id']}: {idea['idea']}")
    data = gemini_json(idea["idea"])
    (WORK_DIR / "script.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (WORK_DIR / "script.txt").write_text(data["script"], encoding="utf-8")
    images = []
    for i in range(1, 7):
        image_path = WORK_DIR / f"image_{i}.jpg"
        generate_image(data[f"image{i}"], image_path, i)
        images.append(image_path)
    audio = WORK_DIR / "audio.mp3"
    make_tts(data["script"], audio)
    captions = WORK_DIR / "captions.srt"
    create_captions(data["script"], data["srt_parts"], TARGET_SECONDS, captions)
    stamp = datetime.now(ZoneInfo("Africa/Cairo")).strftime("%Y%m%d_%H%M%S")
    output = OUTPUT_DIR / f"video_{int(idea['id']):02d}_{safe_slug(data['title'])}_{stamp}.mp4"
    build_video(images, audio, data["script"], captions, output)
    # A successful validated render is the only point at which the idea is consumed.
    mark_used(idea["id"])
    (OUTPUT_DIR / (output.stem + ".json")).write_text(json.dumps({
        "idea_id": idea["id"], "idea": idea["idea"], "title": data["title"],
        "caption": data["caption"], "script": data["script"], "duration_seconds": TARGET_SECONDS,
        "voice": "Fish Audio configured voice", "presenter": "Kombo - consistent young male 3D cartoon host",
        "visual_style": "6-shot cinematic 3D sequence; presenter/cutaway alternation; high-resolution fail-closed image quality gate",
        "image_provider": "Pollinations high-resolution; fail-closed quality gate"
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    gh_output = os.getenv("GITHUB_OUTPUT")
    if gh_output:
        meta_path = OUTPUT_DIR / (output.stem + ".json")
        with open(gh_output, "a", encoding="utf-8") as gh:
            gh.write(f"video=kombo-city-factory/output/{output.name}\n")
            gh.write(f"metadata=kombo-city-factory/output/{meta_path.name}\n")
    print(f"نجاح: {output} ({output.stat().st_size} bytes)")
    print("العنوان:", data["title"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
