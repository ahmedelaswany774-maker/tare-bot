"""Beat grammar. Gemini returns beats; code validates them and derives TTS text (with Fish style tags) and caption words."""
import re
from .objects import OBJECTS
OBJECT_NAMES = list(OBJECTS)
TONES = ("normal", "safe", "danger"); KINDS = ("q", "ok", "bad")
TAG_FIRST, TAG_NEXT, TAG_DANGER = "[excited]", "[energetic]", "[serious]"   # Ahmed picked sample A: excited hook, energetic body

def gemini_schema():
    chip = {"type": "OBJECT", "properties": {"text": {"type": "STRING"}, "tone": {"type": "STRING", "enum": list(TONES)}}, "required": ["text", "tone"]}
    beat = {"type": "OBJECT", "properties": {
        "narration": {"type": "STRING"},
        "objects": {"type": "ARRAY", "items": {"type": "STRING", "enum": OBJECT_NAMES}},
        "chips": {"type": "ARRAY", "items": chip},
        "sticker": {"type": "OBJECT", "properties": {"text": {"type": "STRING"}, "kind": {"type": "STRING", "enum": list(KINDS)}}, "required": ["text", "kind"]},
        "danger": {"type": "BOOLEAN"}}, "required": ["narration", "objects", "chips", "sticker", "danger"]}
    return {"type": "OBJECT", "properties": {"title": {"type": "STRING"}, "caption": {"type": "STRING"}, "beats": {"type": "ARRAY", "items": beat}},
            "required": ["title", "caption", "beats"]}

def validate(data):
    """Raises ValueError for unusable output (so the caller can retry); quietly repairs small things."""
    beats = data.get("beats")
    if not isinstance(beats, list) or not 4 <= len(beats) <= 9: raise ValueError("beats must be 4-9")
    for b in beats:
        if not isinstance(b.get("narration"), str) or not b["narration"].strip(): raise ValueError("empty narration")
        objs = [o for o in b.get("objects", []) if o in OBJECTS][:2]
        if not objs: raise ValueError("beat without a valid object")
        b["objects"] = objs
        b["chips"] = [c for c in b.get("chips", []) if isinstance(c, dict) and c.get("text", "").strip()][:2]
        for c in b["chips"]:
            if c.get("tone") not in TONES: c["tone"] = "normal"
            c["text"] = c["text"].strip()[:28]
        s = b.get("sticker") or {}
        b["sticker"] = {"text": str(s.get("text", "")).strip()[:30], "kind": s.get("kind") if s.get("kind") in KINDS else "q"}
        # red flash only for a real warning: needs a danger chip or a bad sticker (the model over-flags protective beats)
        b["danger"] = bool(b.get("danger")) and (any(c["tone"] == "danger" for c in b["chips"]) or b["sticker"]["kind"] == "bad")
    words = sum(len(b["narration"].split()) for b in beats)
    if not 60 <= words <= 135: raise ValueError(f"narration length {words} words (need 60-135)")
    return data

def clean(text):
    text = re.sub(r"\[[^\]]*\]", " ", text)          # drop any style tags the model added
    return re.sub(r"\s+", " ", text).strip()

def tts_text(beats):
    """Narration with Fish inline style tags, one per beat: excited hook, energetic body, serious on danger beats."""
    out = []
    for i, b in enumerate(beats):
        tag = TAG_DANGER if b["danger"] else (TAG_FIRST if i == 0 else TAG_NEXT)
        out.append(f"{tag} {clean(b['narration'])}")
    return "\n".join(out)

def caption_words(beats):
    """-> (words, beat_first_word_index, hard_end_indexes). Merges 'الـ' with the next word; strips punctuation for display."""
    words, firsts, ends = [], [], set()
    for b in beats:
        raw = clean(b["narration"]).split(); firsts.append(len(words)); i = 0
        while i < len(raw):
            tk = raw[i]; hard = bool(re.search(r"[.!؟?:،,]$", tk))
            if tk.endswith("ـ") and i + 1 < len(raw): i += 1; tk = tk + " " + raw[i]; hard = bool(re.search(r"[.!؟?:،,]$", raw[i]))
            words.append(re.sub(r"[:،,!؟.?]", "", tk).strip() or tk)
            if hard: ends.add(len(words) - 1)
            i += 1
        ends.add(len(words) - 1)
    return words, firsts, ends
