#!/usr/bin/env python3
"""Free-tier educational Shorts factory. One idea -> Arabic voice -> 9:16 MP4."""
from __future__ import annotations

import argparse
import csv
import io
import math
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
MODEL = os.getenv("GEMINI_SCRIPT_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
IMAGE_BASE = "https://gen.pollinations.ai/image/"
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "").strip()
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
# Disable a billing-blocked HF provider for the rest of this run after its first 402.
HF_PROVIDER_DISABLED = False
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell").strip()
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
    # Gemini 503/429 are transient capacity/rate-limit errors. Give the service
    # enough recovery time instead of exhausting all attempts in a few seconds.
    retry_delays = (15, 30, 60, 90, 120)
    for attempt in range(len(retry_delays) + 1):
        try:
            response = SESSION.post(url, params={"key": api_key}, json=payload, timeout=120)
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
            # ReadTimeout/ConnectTimeout/ConnectionError are transient too.
            # The previous logic retried HTTP capacity errors but stopped immediately
            # on a network timeout, which caused avoidable failed production runs.
            retryable = (
                isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
                or (
                    isinstance(exc, RuntimeError)
                    and any(f"Gemini HTTP {code}" in str(exc) for code in (408, 429, 500, 502, 503, 504))
                )
            )
            if not retryable or attempt >= len(retry_delays):
                break
            delay = retry_delays[attempt]
            print(f"Gemini temporary error; retry {attempt + 1}/{len(retry_delays)} in {delay}s: {exc}")
            time.sleep(delay)
    raise RuntimeError(f"تعذر توليد السيناريو بعد إعادة المحاولة الذكية: {last_error}")


def generate_image(prompt: str, destination: Path, scene: int) -> None:
    """Create a polished, topic-aware vertical motion-graphics scene locally; no image API or paid provider."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    w, h = WIDTH, HEIGHT
    seed = sum(ord(ch) for ch in (prompt or "")) + scene * 7919
    rng = random.Random(seed)
    # Deep cinematic gradient with a restrained cyan/amber lighting palette.
    top = (7, 14, 34)
    bottom = (15, 35, 62)
    image = Image.new("RGB", (w, h))
    px = image.load()
    for y in range(h):
        t = y / max(1, h - 1)
        glow = max(0.0, 1.0 - abs(t - (0.35 + scene * 0.035)) / 0.48)
        row = tuple(int(top[c] * (1-t) + bottom[c] * t + (10, 35, 48)[c] * glow) for c in range(3))
        for x in range(w):
            px[x, y] = row
    # Large soft light source behind the hero object.
    glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    cx, cy = w // 2, int(h * (0.43 + (scene % 3) * 0.035))
    for radius, alpha in ((430, 10), (330, 14), (230, 20), (140, 25)):
        gd.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=(30, 190, 230, alpha))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(75))
    image = Image.alpha_composite(image.convert("RGBA"), glow_layer)
    d = ImageDraw.Draw(image, "RGBA")
    # Perspective floor/grid and subtle technical framing.
    horizon = int(h * 0.70)
    for k in range(-8, 9):
        x0 = cx + k * 28
        d.line((cx + k * 8, horizon, x0 * 3 - cx * 2, h), fill=(60, 180, 220, 35), width=2)
    for j in range(1, 9):
        yy = horizon + int((h-horizon) * (j/9) ** 1.7)
        d.line((0, yy, w, yy), fill=(60, 180, 220, 25), width=2)
    # Floating particles add depth without looking like placeholder clipart.
    for _ in range(95):
        x, y = rng.randrange(35, w-35), rng.randrange(100, h-120)
        r = rng.choice((2, 3, 4, 6))
        d.ellipse((x-r, y-r, x+r, y+r), fill=(105, 220, 245, rng.randrange(35, 115)))
    # Determine the visual family from the scene prompt and idea vocabulary.
    words = (prompt or "").lower()
    is_cpu = any(k in words for k in ("cpu", "processor", "معالج", "بروسيسور", "كمبيوتر", "computer"))
    is_phone = any(k in words for k in ("phone", "mobile", "smartphone", "موبايل", "هاتف"))
    is_network = any(k in words for k in ("internet", "network", "شبكة", "اتصال", "بيانات", "data"))
    is_energy = any(k in words for k in ("energy", "power", "طاقة", "كهرب", "بطارية", "battery"))
    # Alternate camera composition across the six shots while keeping one coherent visual identity.
    if is_cpu:
        size = 430 if scene % 2 else 360
        x1, y1 = cx-size//2, cy-size//2
        x2, y2 = cx+size//2, cy+size//2
        # CPU pins and ceramic substrate.
        for q in range(-5, 6):
            off = q * 38
            d.line((x1+off+size//2, y1-58, x1+off+size//2, y1), fill=(120, 210, 235, 210), width=12)
            d.line((x1+off+size//2, y2, x1+off+size//2, y2+58), fill=(120, 210, 235, 210), width=12)
            d.line((x1-58, y1+off+size//2, x1, y1+off+size//2), fill=(120, 210, 235, 210), width=12)
            d.line((x2, y1+off+size//2, x2+58, y1+off+size//2), fill=(120, 210, 235, 210), width=12)
        d.rounded_rectangle((x1-20,y1-20,x2+20,y2+20), radius=42, fill=(18,38,62,245), outline=(65,205,235,230), width=8)
        d.rounded_rectangle((x1+35,y1+35,x2-35,y2-35), radius=28, fill=(7,18,37,255), outline=(225,165,82,230), width=5)
        for q in range(5):
            yy = y1+90+q*58
            d.line((x1+85,yy,x2-85,yy), fill=(50,170,215,100), width=3)
        d.rounded_rectangle((cx-95,cy-95,cx+95,cy+95), radius=24, fill=(23,76,104,255), outline=(110,230,245,255), width=7)
        d.rectangle((cx-50,cy-50,cx+50,cy+50), fill=(38,130,157,255), outline=(225,190,110,255), width=4)
        for q in range(7):
            xx = x1 + 70 + q*48
            d.line((xx,y1+12,xx,y1-105-rng.randrange(0,45)), fill=(80,205,230,140), width=3)
    elif is_phone:
        pw, ph = 360, 690
        x1, y1 = cx-pw//2, cy-ph//2
        d.rounded_rectangle((x1-18,y1-18,x1+pw+18,y1+ph+18), radius=70, fill=(135,170,190,255), outline=(215,235,245,255), width=8)
        d.rounded_rectangle((x1,y1,x1+pw,y1+ph), radius=58, fill=(5,18,36,255), outline=(55,190,220,255), width=6)
        d.rounded_rectangle((x1+22,y1+35,x1+pw-22,y1+ph-35), radius=35, fill=(13,55,78,255))
        for q in range(5):
            yy = y1+150+q*88
            d.rounded_rectangle((x1+55,yy,x1+pw-55,yy+42), radius=18, fill=(35+q*7,125+q*8,155+q*8,220))
        d.ellipse((cx-30,y1+ph-65,cx+30,y1+ph-5), outline=(140,225,240,220), width=5)
    elif is_network or is_energy:
        nodes = []
        for q in range(11):
            angle = (q/11)*6.283 + scene*0.2
            radius = rng.randint(180, 360)
            nx = cx + int(math.cos(angle)*radius)
            ny = cy + int(math.sin(angle)*radius*0.82)
            nodes.append((nx,ny))
        for q, (nx,ny) in enumerate(nodes):
            for mx,my in nodes[q+1:]:
                if (nx-mx)**2+(ny-my)**2 < 170000:
                    d.line((nx,ny,mx,my), fill=(65,190,225,85), width=4)
        for nx,ny in nodes:
            d.ellipse((nx-25,ny-25,nx+25,ny+25), fill=(30,125,160,230), outline=(135,230,245,255), width=5)
        d.ellipse((cx-125,cy-125,cx+125,cy+125), fill=(20,78,105,245), outline=(240,185,100,255), width=9)
        d.ellipse((cx-65,cy-65,cx+65,cy+65), fill=(70,180,195,255))
    else:
        # A cinematic abstract "idea core": layered glass rings and luminous centerpiece.
        for q, radius in enumerate((330,270,205,135)):
            bbox=(cx-radius,cy-radius,cx+radius,cy+radius)
            d.ellipse(bbox, outline=(65+q*25,185+q*10,225,150+q*20), width=8 if q<2 else 5)
        d.ellipse((cx-115,cy-115,cx+115,cy+115), fill=(20,95,125,245), outline=(145,235,245,255), width=8)
        d.ellipse((cx-62,cy-62,cx+62,cy+62), fill=(230,170,85,255))
        for q in range(8):
            angle=q*math.pi/4
            ex=cx+int(math.cos(angle)*390); ey=cy+int(math.sin(angle)*320)
            d.line((cx,cy,ex,ey), fill=(75,190,220,80), width=4)
            d.ellipse((ex-13,ey-13,ex+13,ey+13), fill=(125,225,240,220))
    # Shot-specific HUD accents and cinematic frame.
    d.rounded_rectangle((38,45,w-38,h-45), radius=34, outline=(110,205,225,65), width=3)
    d.line((70,125,260,125), fill=(235,175,90,220), width=7)
    d.line((w-260,h-125,w-70,h-125), fill=(65,205,230,180), width=7)
    # Slight bloom and grain-like texture keep the render polished after video zoom.
    image = image.convert("RGB").filter(ImageFilter.GaussianBlur(0.25))
    image.save(destination, "JPEG", quality=94, optimize=True)
    with Image.open(destination) as check:
        if check.size != (WIDTH, HEIGHT):
            raise RuntimeError(f"Local scene has wrong dimensions: {check.size}.")
    print(f"Local motion-graphics scene {scene}/6 ready (Pillow; no image API).")

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
    fps_value = video.get("avg_frame_rate", "0/1") if video else "0/1"
    try:
        fps_num, fps_den = (int(x) for x in fps_value.split("/", 1))
        actual_fps = fps_num / fps_den if fps_den else 0
    except (TypeError, ValueError, ZeroDivisionError):
        actual_fps = 0
    if (not video or not audio_stream
            or int(video["width"]) != WIDTH or int(video["height"]) != HEIGHT
            or abs((int(video["width"]) / int(video["height"])) - (9 / 16)) > 0.0001
            or abs(actual_fps - FPS) > 0.1):
        raise RuntimeError(
            f"فشل فحص صيغة YouTube Shorts: expected {WIDTH}x{HEIGHT} (9:16) at {FPS}fps; "
            f"got {video.get('width') if video else 'no-video'}x{video.get('height') if video else 'no-video'} "
            f"at {actual_fps:.3f}fps."
        )
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
        "image_provider": "Local Pillow cinematic motion graphics (no image API)"
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
