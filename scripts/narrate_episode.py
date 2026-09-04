"""Generate narration using the owner's local XTTS reference, without a cloud TTS call."""
import argparse
import re
import subprocess
from pathlib import Path


def split_text(text, max_chars=280):
    chunks = []
    current = ""
    for sentence in re.split(r"(?<=[.!؟?\n])\s+", text.strip()):
        for word in sentence.split():
            if len(word) > max_chars:
                raise ValueError("كلمة تتجاوز الحد الأقصى لمحرك الصوت")
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if len(current) > max_chars // 2:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("script")
    parser.add_argument("--reference", default="voice_reference.wav")
    parser.add_argument("--output", default="room-17-part-04-voice.mp3")
    args = parser.parse_args()
    reference = Path(args.reference)
    if not reference.is_file():
        raise FileNotFoundError("ملف بصمتك الصوتية غير موجود؛ لن يُستخدم صوت بديل")
    chunks = split_text(Path(args.script).read_text(encoding="utf-8"))
    if not chunks:
        raise ValueError("نص الحلقة فارغ")
    import torch
    from TTS.api import TTS
    torch.set_num_threads(2)
    model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)
    folder = Path("episode_voice_chunks")
    folder.mkdir(exist_ok=True)
    outputs = []
    for index, text in enumerate(chunks):
        output = folder / f"chunk-{index:04d}.wav"
        model.tts_to_file(text=text, file_path=str(output), speaker_wav=str(reference), language="ar", split_sentences=False)
        outputs.append(output.resolve())
        print(f"اكتمل جزء الصوت {index + 1}/{len(chunks)}", flush=True)
    listing = folder / "concat.txt"
    listing.write_text("".join(f"file '{path}'\n" for path in outputs), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "24000", "-ac", "1", args.output,
    ], check=True)
    print(f"اكتمل التعليق الصوتي ببصمتك: {args.output}", flush=True)


if __name__ == "__main__":
    main()
