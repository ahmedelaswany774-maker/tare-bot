"""Beat renderer: fixed stage, one or two objects per beat on a conveyor, one-word captions, chips with connectors,
bottom sticker, red danger flash + shake on danger beats. Streams raw frames into ffmpeg, muxes the narration audio."""
import math, subprocess, time
import numpy as np
from PIL import Image, ImageChops
from .core import *
from .objects import OBJECTS

TONE = {"normal": CYAN, "safe": GREEN, "danger": RED}
def conv(t, a, b, cx, enter=.55, exit_=.4):
    if t < a - .05 or t > b + .45: return None
    if t < a + enter - .05: return cx + (1 - ease_back((t - (a - .05)) / enter, 1.1)) * 900
    if t > b - .05: return cx - ease_io((t - (b - .05)) / exit_) * 1100
    return cx

def render(beats, words, firsts, audio, dur, out, logo="كومبو", log=print):
    """words: [(display, start, end)], firsts: index of each beat's first word, dur: audio seconds."""
    starts = [0.0] + [words[i][1] - .12 for i in firsts[1:]]
    ends = starts[1:] + [dur + .6]
    total = dur + .6
    stage = make_stage(); lg = make_logo(logo); cap_cache = {}
    prep = []
    for i, b in enumerate(beats):
        chips = [make_chip(c["text"], TONE[c["tone"]], size=44 if len(c["text"]) <= 18 else 36) for c in b["chips"]]
        st = make_sticker(b["sticker"]["text"], b["sticker"]["kind"]) if b["sticker"]["text"] else None
        prep.append((chips, st))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    n = int(total * FPS); t0 = time.time()
    try:
        for f in range(n):
            t = f / FPS; fr = stage.copy(); fr.alpha_composite(lg, (930 - 70, 60))
            bi = max(i for i in range(len(beats)) if t >= starts[i] - .05) if t >= starts[0] else 0
            shake = 0; flash = 0.0
            for i in (bi - 1, bi):
                if i < 0: continue
                b = beats[i]; a, e = starts[i], ends[i]; p = t - a; chips, st = prep[i]
                objs = b["objects"]; bob = 3 * math.sin(t * 2.2)
                pos = [(W // 2, 1.0)] if len(objs) == 1 else [(300, .78), (790, .78)]
                tops = []
                for k, name in enumerate(objs):
                    cx0, sc = pos[k]; x = conv(t, a + (0 if k == 0 else .12), e, cx0)
                    if x is None: tops.append(None); continue
                    spr = OBJECTS[name](t, max(p, 0)); bx, by = place(fr, spr, x, BASE_Y + 4 + bob * .4, sc); tops.append((x, by, spr.width * sc, spr.height * sc))
                if i != bi: continue
                # chips: chip k attaches to object k (two objects) or both attach to object 0 (one object)
                for k, chip in enumerate(chips):
                    ob = tops[k] if len(objs) > 1 and k < len(tops) else tops[0]
                    if not ob: continue
                    x, by, ow, oh = ob
                    if len(objs) > 1: cxp, cyp, tx, ty = x, by - 70, x, by + 20
                    elif k == 0: cxp, cyp, tx, ty = x - 170, by - 70, x - 70, by + oh * .3
                    else: cxp, cyp, tx, ty = x + 170, by + oh * .55, x + 60, by + oh * .65
                    cxp = min(max(cxp, chip.width / 2 + 20), W - chip.width / 2 - 20); cyp = max(cyp, 520)
                    tstart = a + 0.9 + .55 * k
                    pop_paste(fr, chip, cxp, cyp, ease_out((t - tstart) / .4))
                    connector(fr, (cxp, cyp + chip.height // 2 - 10), (tx, ty), TONE[b["chips"][k]["tone"]], ease_out((t - tstart - .2) / .3))
                if st is not None and a + .9 <= t < e - .1:
                    k = ease_back((t - a - .9) / .4, 1.5); s = st
                    if s.width > W - 40: s = s.resize((W - 40, int(s.height * (W - 40) / s.width)))
                    fr.alpha_composite(s, (int((W - s.width) / 2), int(1590 + (1 - min(k, 1)) * 140)))
                if b["danger"] and p < .7:
                    flash = max(0, 1 - p / .7) * (.5 + .5 * math.cos(p * 28)); shake = int(16 * max(0, 1 - p / .7) * math.sin(p * 60))
            # caption: one word at a time
            cur = None
            for i, (tk, s, e) in enumerate(words):
                if s <= t: cur = (tk, s)
                else: break
            if cur and t < words[-1][2] + 1:
                tk, s = cur
                if tk not in cap_cache:
                    ci = text_img(tk, 150, fill=WHITE, stroke=9, stroke_fill=(8, 16, 40), shadow=True)
                    if ci.width > 980: ci = ci.resize((980, int(ci.height * 980 / ci.width)), Image.LANCZOS)
                    cap_cache[tk] = ci
                ci = cap_cache[tk]; sc = 1 + .16 * (1 - ease_out((t - s) / .12))
                if sc != 1: ci = ci.resize((int(ci.width * sc), int(ci.height * sc)), Image.BILINEAR)
                fr.alpha_composite(ci, (int((W - ci.width) / 2), int(330 - ci.height / 2)))
            if flash > 0.01:
                ov = Image.new("RGBA", (W, H), (230, 30, 40, int(150 * flash))); fr.alpha_composite(ov)
            img = fr.convert("RGB")
            if shake: img = ImageChops.offset(img, shake, shake // 2)
            ff.stdin.write(np.asarray(img).tobytes())
            if f % 300 == 0: log(f"render {f}/{n} ({time.time()-t0:.0f}s)")
    finally:
        ff.stdin.close(); ff.wait()
    return out
