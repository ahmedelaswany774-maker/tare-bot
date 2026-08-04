"""
Orchestrates final video rendering on Kaggle:
1. Copies story.mp3 + all clip_*.mp4 + a small manifest into the kernel dir
2. Pushes it as a Kaggle kernel (`kaggle kernels push`)
3. Polls kernel status until it finishes (or times out)
4. Downloads the rendered story.mp4

Requires KAGGLE_USERNAME and KAGGLE_KEY environment variables (from GitHub
Secrets). If they're missing, or anything here fails, the caller should fall
back to rendering locally with moviepy (already optimized separately).
"""

import json
import os
import shutil
import subprocess
import tempfile
import time

WORKER_DIR = os.path.join(os.path.dirname(__file__), "kaggle_worker")
POLL_INTERVAL_SECONDS = 20
DEFAULT_TIMEOUT_SECONDS = 900  # 15 minutes: upload + queue + render + download


def _kaggle_available():
    return bool(os.environ.get("KAGGLE_USERNAME")) and bool(os.environ.get("KAGGLE_KEY"))


def _run(cmd, cwd=None, timeout=120):
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return -1, "", str(e)


def render_video_via_kaggle(audio_path, clip_files, target_duration, output_path,
                             timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    """Returns True and writes the rendered video to output_path on success.
    Returns False (never raises) if Kaggle isn't configured or anything
    fails, so the caller can fall back to local rendering."""

    if not _kaggle_available():
        print("ℹ️ Kaggle غير مُعد (KAGGLE_USERNAME/KAGGLE_KEY غير موجودين)، تخطي")
        return False

    username = os.environ["KAGGLE_USERNAME"]
    kernel_id = f"{username}/tare-bot-video-render"

    with tempfile.TemporaryDirectory() as tmp:
        # 1) Assemble the kernel push directory
        shutil.copy(os.path.join(WORKER_DIR, "render_video.py"), tmp)
        with open(os.path.join(WORKER_DIR, "kernel-metadata.json"), "r", encoding="utf-8") as f:
            meta = f.read().replace("__KAGGLE_USERNAME__", username)
        with open(os.path.join(tmp, "kernel-metadata.json"), "w", encoding="utf-8") as f:
            f.write(meta)

        shutil.copy(audio_path, os.path.join(tmp, "story.mp3"))
        for i, clip in enumerate(clip_files):
            shutil.copy(clip, os.path.join(tmp, f"clip_{i:03d}.mp4"))
        with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"target_duration": target_duration}, f)

        total_size_mb = sum(
            os.path.getsize(os.path.join(tmp, f)) for f in os.listdir(tmp)
        ) / (1024 * 1024)
        print(f"🚀 بعت {len(clip_files)} كليب + الصوت ({total_size_mb:.1f} MB) لـ Kaggle...")

        # 2) Push the kernel
        code, out, err = _run(["kaggle", "kernels", "push", "-p", tmp], timeout=300)
        if code != 0:
            print(f"❌ فشل رفع الـ kernel لـ Kaggle: {err or out}")
            return False

        # 3) Poll until done
        deadline = time.time() + timeout_seconds
        status = None
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
            code, out, err = _run(["kaggle", "kernels", "status", kernel_id], timeout=60)
            if code != 0:
                print(f"⚠️ تعذر التحقق من حالة الـ kernel: {err or out}")
                continue
            status = out.strip()
            print(f"   ⏳ حالة Kaggle: {status}")
            if "complete" in status.lower():
                break
            if "error" in status.lower() or "cancel" in status.lower():
                print(f"❌ فشل الرندر على Kaggle: {status}")
                return False
        else:
            print(f"❌ انتهت المهلة ({timeout_seconds}s) قبل ما Kaggle يخلص")
            return False

        if not status or "complete" not in status.lower():
            return False

        # 4) Download the rendered video
        download_dir = tempfile.mkdtemp()
        code, out, err = _run(
            ["kaggle", "kernels", "output", kernel_id, "-p", download_dir, "--force"],
            timeout=300,
        )
        if code != 0:
            print(f"❌ فشل تنزيل الفيديو من Kaggle: {err or out}")
            return False

        candidate = os.path.join(download_dir, "output", "story.mp4")
        if not os.path.exists(candidate):
            candidate = os.path.join(download_dir, "story.mp4")
        if not os.path.exists(candidate) or os.path.getsize(candidate) == 0:
            print("❌ الفيديو المُرندر مش موجود في نتيجة Kaggle")
            return False

        shutil.copy(candidate, output_path)
        print(f"✅ اتنزل الفيديو من Kaggle بنجاح -> {output_path}")
        return True
