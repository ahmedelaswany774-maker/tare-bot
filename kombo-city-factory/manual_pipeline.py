#!/usr/bin/env python3
"""Gemini app image handoff for Kombo City Factory."""
from __future__ import annotations
import argparse, csv, json, os, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageStat
import main as factory

ROOT = Path(__file__).resolve().parent
PENDING, INBOX = ROOT / "pending", ROOT / "inbox"

def prepare():
    PENDING.mkdir(parents=True, exist_ok=True)
    used = factory.load_used()
    pending_ids = {p.name.removeprefix('idea_') for p in PENDING.iterdir()
                   if p.is_dir() and p.name.startswith('idea_')}
    with factory.IDEAS_FILE.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    choices = [r for r in rows if r.get('id') and r['id'] not in used
               and r['id'] not in pending_ids and r.get('status', 'unused') != 'used']
    if not choices:
        raise RuntimeError('لا توجد فكرة جديدة غير مستخدمة أو قيد التجهيز.')
    idea = sorted(choices, key=lambda r: int(r['id']))[0]
    folder = PENDING / f"idea_{idea['id']}"
    folder.mkdir(parents=True, exist_ok=False)
    inbox_folder = INBOX / folder.name
    inbox_folder.mkdir(parents=True, exist_ok=True)
    (inbox_folder / '.gitkeep').write_text('', encoding='utf-8')
    template = factory.PROMPT_FILE.read_text(encoding='utf-8')
    prompt = template.replace('{idea}', idea['idea'])
    instructions = [
        f"# كومبو — الفكرة رقم {idea['id']}", '',
        f"**الفكرة:** {idea['idea']}", '',
        '## المطلوب من تطبيق Gemini',
        'انسخ النص التالي كاملًا إلى تطبيق Gemini. احفظ الناتج JSON باسم content.json داخل مجلد pending/idea_{idea['id']}/. لا تضع Markdown أو شرحًا خارج JSON.',
        '', '```text', prompt, '```', '',
        '## الصور الستة',
        'استخدم أوصاف image1 إلى image6 لتوليد ست صور منفصلة عمودية 9:16، بدون كتابة أو شعارات أو كولاج.',
        'ارفع الصور إلى kombo-city-factory/inbox/idea_{idea['id']}/ بالأسماء scene_1.jpg إلى scene_6.jpg.',
        '', 'بعد رفع content.json والصور الستة، يبدأ التصيير والصوت تلقائيًا عند وصول الصور.'
    ]
    (folder / 'prompt.md').write_text('\n'.join(instructions), encoding='utf-8')
    print(f"Gemini app prompt ready: {folder / 'prompt.md'}")
    print(f"Save Gemini JSON as: {folder / 'content.json'}")
    print(f"Upload six images to: kombo-city-factory/inbox/{folder.name}/")
    return 0
def normalize_image(source, destination, scene):
    try:
        with Image.open(source) as original:
            image = original.convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"الصورة {scene} غير صالحة: {exc}") from exc
    ratio = image.width / image.height
    if image.width < 512 or image.height < 900 or not 0.52 <= ratio <= 0.62:
        raise RuntimeError(f"الصورة {scene} يجب أن تكون عمودية 9:16؛ المقاس {image.width}x{image.height}.")
    probe = image.resize((96, 160), Image.Resampling.LANCZOS).convert("L")
    if ImageStat.Stat(probe).mean[0] < 12:
        raise RuntimeError(f"الصورة {scene} شديدة الظلام.")
    target = 9 / 16
    if ratio > target:
        width = round(image.height * target)
        left = (image.width - width) // 2
        image = image.crop((left, 0, left + width, image.height))
    elif ratio < target:
        height = round(image.width / target)
        top = (image.height - height) // 2
        image = image.crop((0, top, image.width, top + height))
    image.resize((factory.WIDTH, factory.HEIGHT), Image.Resampling.LANCZOS).save(
        destination, "JPEG", quality=94, optimize=True)

def render_pending():
    folders = sorted((p for p in PENDING.glob("idea_*") if p.is_dir()),
                     key=lambda p: int(p.name.split("_", 1)[1]))
    selected = None
    for folder in folders:
        inbox = INBOX / folder.name
        if (folder / "content.json").exists() and all((inbox / f"scene_{n}.jpg").exists() for n in range(1, 7)):
            selected = folder, inbox
            break
    if not selected:
        raise RuntimeError("لم أجد content.json مع الصور الستة. ارفع JSON إلى pending/idea_<ID>/content.json والصور إلى inbox/idea_<ID>/.")
    folder, inbox = selected
    with factory.IDEAS_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        idea = next(r for r in csv.DictReader(f) if r["id"] == folder.name.removeprefix("idea_"))
    data = json.loads((folder / "content.json").read_text(encoding="utf-8"))
    required = ("script", "image1", "image2", "image3", "image4", "image5", "image6", "title", "caption", "srt_parts")
    if any(not data.get(k) for k in required) or len(data["srt_parts"]) != 6:
        raise RuntimeError("content.json ناقص أو لا يحتوي المفاتيح العشرة المطلوبة.")
    if not 65 <= len(data["script"].split()) <= 115:
        raise RuntimeError("طول السيناريو يجب أن يكون بين 65 و115 كلمة.")
    print(f"Rendering idea #{idea['id']}: {idea['idea']}")
    factory.require_tools()
    factory.WORK_DIR.mkdir(parents=True, exist_ok=True)
    factory.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    images = []
    for n in range(1, 7):
        dest = factory.WORK_DIR / f"image_{n}.jpg"
        normalize_image(inbox / f"scene_{n}.jpg", dest, n)
        images.append(dest)
    audio = factory.WORK_DIR / "audio.mp3"
    factory.make_tts(data["script"], audio)
    captions = factory.WORK_DIR / "captions.srt"
    factory.create_captions(data["script"], data["srt_parts"], factory.TARGET_SECONDS, captions)
    stamp = datetime.now(ZoneInfo("Africa/Cairo")).strftime("%Y%m%d_%H%M%S")
    output = factory.OUTPUT_DIR / f"video_{int(idea['id']):02d}_{factory.safe_slug(data['title'])}_{stamp}.mp4"
    factory.build_video(images, audio, data["script"], captions, output)
    meta = {"idea_id": idea["id"], "idea": idea["idea"], "title": data["title"],
            "caption": data["caption"], "script": data["script"],
            "duration_seconds": factory.TARGET_SECONDS, "voice": "Fish Audio configured voice",
            "image_provider": "Gemini app Nano Banana, user supplied"}
    meta_path = factory.OUTPUT_DIR / (output.stem + ".json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    factory.mark_used(str(idea["id"]))
    gh = os.getenv("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"video=kombo-city-factory/output/{output.name}\n")
            f.write(f"metadata=kombo-city-factory/output/{meta_path.name}\n")
    print(f"Validated video ready: {output}")
    return 0

def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--render-pending", action="store_true")
    args = parser.parse_args()
    return prepare() if args.prepare else render_pending()

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
