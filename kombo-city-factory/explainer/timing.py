"""Word timing without any paid API. Fish Audio returns no timestamps, so words are placed on the real speech
(ffmpeg silencedetect) with sentence/beat ends snapped to the nearest real pause. Weighted by character count."""
import re, subprocess
import numpy as np

def duration(audio):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio], capture_output=True, text=True)
    return float(r.stdout.strip())

def pauses(audio, noise="-32dB", d=0.13):
    r = subprocess.run(["ffmpeg", "-i", audio, "-af", f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"], capture_output=True, text=True)
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    out = []
    for i, s in enumerate(st): out.append((s, en[i] if i < len(en) else duration(audio)))
    return out

def _map(words, a, b, inner):
    """place words (list of str) into [a,b] skipping inner pauses, weight by chars. returns [(s,e)]"""
    segs, cur = [], a
    for p0, p1 in sorted(inner):
        if p1 <= a or p0 >= b: continue
        p0, p1 = max(p0, a), min(p1, b)
        if p0 > cur: segs.append((cur, p0))
        cur = max(cur, p1)
    if cur < b: segs.append((cur, b))
    if not segs: segs = [(a, b)]
    total = sum(e - s for s, e in segs); wts = [len(w) + 1 for w in words]; cum = np.cumsum([0] + wts) / sum(wts)
    def at(f):
        tt = f * total
        for s, e in segs:
            if tt <= e - s: return s + tt
            tt -= e - s
        return segs[-1][1]
    return [(at(cum[i]), at(cum[i + 1])) for i in range(len(words))]

def align(words, hard_ends, audio):
    """words: display tokens. hard_ends: set of word indexes after which a pause is expected (sentence/beat ends).
    returns [(word, start, end)] and the pause list used."""
    D = duration(audio); P = [p for p in pauses(audio)]
    lead = P[0][1] if P and P[0][0] < .15 else 0.0
    trail = P[-1][0] if P and P[-1][1] >= D - .15 else D
    P = [p for p in P if p[0] > lead + .05 and p[1] < trail - .05]
    first = _map(words, lead, trail, P)
    used, anchors = set(), {}
    for idx in sorted(hard_ends):
        if idx >= len(words) - 1: continue
        pred = first[idx][1]
        best, bd = None, 1.6
        for j, (p0, p1) in enumerate(P):
            if j in used or p1 - p0 < .18: continue
            dist = abs((p0 + p1) / 2 - pred)
            if dist < bd: best, bd = j, dist
        if best is not None: used.add(best); anchors[idx] = P[best]
    pts = [(-1, lead, lead)] + [(i, anchors[i][0], anchors[i][1]) for i in sorted(anchors)] + [(len(words) - 1, trail, trail)]
    out = []
    for k in range(len(pts) - 1):
        i0, _, a = pts[k]; i1, b, _ = pts[k + 1]
        ws = words[i0 + 1:i1 + 1]
        if not ws: continue
        inner = [p for j, p in enumerate(P) if j not in used]
        for (s, e), w in zip(_map(ws, a, b, inner), ws): out.append((w, s, e))
    return out, D, len(anchors)

def whisper_words(audio, model="base"):
    """Real speech timestamps from faster-whisper (free, CPU, int8). The Arabic text it returns is noisy and is NOT used;
    only when speech happens is used. Returns [(chars, start, end)]."""
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language="ar", word_timestamps=True, beam_size=1, vad_filter=False)
    return [(max(1, len(w.word.strip())), w.start, w.end) for s in segs for w in s.words]

def align_whisper(words, audio, model="base"):
    """Map the script's words onto the real speech profile: script char-fraction -> whisper char-fraction -> time."""
    ww = whisper_words(audio, model)
    if len(ww) < max(5, len(words) // 4): raise RuntimeError("whisper returned too few words")
    tot = float(sum(c for c, _, _ in ww)); xp, fp, cum = [], [], 0.0
    for c, s, e in ww:
        xp += [cum / tot + 1e-7 * len(xp), (cum + c) / tot + 1e-7 * (len(xp) + 1)]; fp += [s, e]; cum += c
    xp = np.maximum.accumulate(np.array(xp)); fp = np.maximum.accumulate(np.array(fp))
    wts = [len(w) + 1 for w in words]; cw = np.cumsum([0] + wts) / sum(wts)
    out = []
    for i, w in enumerate(words):
        s = float(np.interp(cw[i] + 5e-7, xp, fp)); e = float(np.interp(cw[i + 1] - 5e-7, xp, fp))
        out.append((w, s, max(e, s + .05)))
    return out, duration(audio)

def best_align(words, hard_ends, audio, log=print):
    """Whisper timing if available, otherwise pause-based fallback."""
    try:
        tw, D = align_whisper(words, audio); log("word timing: faster-whisper")
        return snap(tw, hard_ends, audio), D
    except Exception as exc:
        log(f"word timing: whisper unavailable ({exc}); using pause-based fallback")
        tw, D, _ = align(words, hard_ends, audio); return tw, D

def snap(tw, hard_ends, audio, win=1.0):
    """Snap each sentence/beat end onto the nearest real pause (whisper timestamps blur around pauses)."""
    P = [p for p in pauses(audio) if p[1] - p[0] >= .18]; used = set(); tw = [list(x) for x in tw]
    for i in sorted(hard_ends):
        if i >= len(tw) - 1: continue
        ref = tw[i][2]; best, bd = None, win
        for j, (p0, p1) in enumerate(P):
            d = abs(p0 - ref) if p0 <= ref else abs(p1 - ref) if p1 > ref and p0 > ref else 0
            d = min(abs(p0 - ref), abs(p1 - ref), abs((p0 + p1) / 2 - ref))
            if j not in used and d < bd: best, bd = j, d
        if best is None: continue
        p0, p1 = P[best]
        if p0 > tw[i][1] + .05 and p1 < tw[i + 1][2] - .05:
            used.add(best); tw[i][2] = p0; tw[i + 1][1] = p1
    tw[0][1] = max(0.0, tw[0][1])
    return [tuple(x) for x in tw]
