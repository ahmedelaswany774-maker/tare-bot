"""Explainer-style renderer (reference: 'من الصفر' reels). 1080x1920 @30fps. Pure Pillow + numpy + ffmpeg pipe.
Fixed stage (blueprint grid + wooden table), glossy locally-drawn 2.5D objects that slide in on a conveyor, one-word kinetic captions,
spec chips with connector lines, bottom quiz stickers, optional red danger flash."""
import math, subprocess, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

W, H, FPS = 1080, 1920, 30
NAVY = (14, 26, 58); GRID = (60, 96, 160)
YELLOW = (250, 204, 40); WHITE = (250, 252, 255); RED = (230, 56, 60); GREEN = (46, 190, 110); CYAN = (70, 200, 240); GOLD = (244, 184, 70)
import os
_FD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
AR_B = os.path.join(_FD, "NotoSansArabic-Black.ttf")
AR_M = os.path.join(_FD, "NotoSansArabic-Bold.ttf")
LA_B = os.path.join(_FD, "NotoSans-Black.ttf")
TABLE_TOP, TABLE_FRONT_END = 1196, 1330
BASE_Y = 1230

_fc = {}
def F(path, size):
    k = (path, size)
    if k not in _fc: _fc[k] = ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)
    return _fc[k]
def is_latin(tok): return any("a" <= c.lower() <= "z" for c in tok)
def tokens_layout(text, size, ar_path=AR_B):
    """Visual left->right parts for RTL text. Latin/digits/= use a Latin font; punctuation like ؟ stays Arabic."""
    d0 = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    logical = []
    for tk in text.split():
        if is_latin(tk) or tk in ("=", "+", "-", "×", "/", "%", "→"):
            core = tk.rstrip("؟،:!.?")
            logical.append(("L", core)); tail = tk[len(core):]
            if tail: logical.append(("A", tail))
        else: logical.append(("A", tk))
    parts = []
    for kind, tk in logical:
        if kind == "L": f = F(LA_B, int(size * .86)); s = tk
        else: f = F(ar_path, size); s = get_display(arabic_reshaper.reshape(tk))
        parts.append((s, f, d0.textlength(s, font=f)))
    gap = size * .28
    return parts[::-1], gap
def text_img(text, size, fill=WHITE, stroke=0, stroke_fill=(10, 18, 40), ar_path=AR_B, shadow=False):
    parts, gap = tokens_layout(text, size, ar_path)
    tw = int(sum(p[2] for p in parts) + gap * (len(parts) - 1)); pad = stroke + 10
    im = Image.new("RGBA", (tw + pad * 2, int(size * 1.9) + pad * 2), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x = pad; base = pad + int(size * 1.25)
    for s, f, w in parts:
        if shadow: d.text((x + 3, base + 6), s, font=f, fill=(0, 0, 0, 120), stroke_width=stroke, stroke_fill=(0, 0, 0, 120), anchor="ls")
        d.text((x, base), s, font=f, fill=fill + (255,), stroke_width=stroke, stroke_fill=stroke_fill + (255,), anchor="ls")
        x += w + gap
    bb = im.getbbox(); return im.crop(bb) if bb else im
def ease_out(x): x = min(max(x, 0), 1); return 1 - (1 - x) ** 3
def ease_back(x, s=1.4): x = min(max(x, 0), 1) - 1; return 1 + (s + 1) * x ** 3 + s * x ** 2
def ease_io(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)
def noise(w, h, seed, sigma):
    n = np.random.default_rng(seed).normal(0, 1, (h, w)).astype("float32")
    im = Image.fromarray(np.clip(n * 40 + 128, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(sigma))
    return (np.array(im).astype("float32") - 128) / 40

def glow(r, color, a=255, p=2.0):
    S = r * 2; yy, xx = np.mgrid[0:S, 0:S].astype("float32")
    al = np.clip(1 - np.sqrt((xx - r) ** 2 + (yy - r) ** 2) / r, 0, 1) ** p * a
    arr = np.zeros((S, S, 4), "uint8"); arr[..., :3] = color; arr[..., 3] = al.astype("uint8")
    return Image.fromarray(arr)

def make_stage():
    y = np.linspace(0, 1, H, dtype="float32")[:, None]
    a = np.zeros((H, W, 3), "float32")
    a[..., 0] = 12 + 10 * y; a[..., 1] = 24 + 14 * y; a[..., 2] = 56 + 22 * y
    im = Image.fromarray(a.astype("uint8")).convert("RGBA"); d = ImageDraw.Draw(im, "RGBA")
    for x in range(0, W + 1, 60): d.line((x, 0, x, TABLE_TOP), fill=GRID + ((70 if x % 300 == 0 else 34),), width=2 if x % 300 == 0 else 1)
    for yy in range(0, TABLE_TOP, 60): d.line((0, yy, W, yy), fill=GRID + ((70 if yy % 300 == 0 else 34),), width=2 if yy % 300 == 0 else 1)
    for r in (520, 760): d.arc((W - r, -r + 120, W + r, r + 120), 90, 180, fill=(255, 255, 255, 30), width=3)
    # soft light behind the stage
    im.alpha_composite(glow(700, (60, 110, 200), 70, 1.6), (W // 2 - 700, 700 - 700 + 100))
    # wooden table: top face + front face with grain
    tb = np.zeros((TABLE_FRONT_END - TABLE_TOP, W, 3), "float32")
    top_h = 56
    grain = noise(W, tb.shape[0], 5, 1.0) * 6 + noise(W, tb.shape[0], 9, 24) * 5
    tb[:top_h] = np.array([186, 122, 62], "float32") + grain[:top_h, :, None] * 1.6
    tb[top_h:] = np.array([128, 78, 38], "float32") + grain[top_h:, :, None] * 1.3
    tb[:3] += 40; tb[top_h:top_h + 4] += 24
    tb[top_h:] *= np.linspace(1.0, .72, tb.shape[0] - top_h, dtype="float32")[:, None, None]
    im.alpha_composite(Image.fromarray(np.clip(tb, 0, 255).astype("uint8")).convert("RGBA"), (0, TABLE_TOP))
    # table shadow under the front edge
    sh = Image.new("RGBA", (W, 160), (0, 0, 0, 0)); ImageDraw.Draw(sh).rectangle((0, 0, W, 50), fill=(0, 0, 0, 130))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26)), (0, TABLE_FRONT_END - 10))
    arr = np.array(im.convert("RGB")).astype("float32")
    yy, xx = np.mgrid[0:H, 0:W].astype("float32")
    vig = 1 - 0.38 * (((xx - W / 2) / (W * .7)) ** 2 + ((yy - H / 2) / (H * .62)) ** 2)
    arr *= np.clip(vig, .35, 1)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).convert("RGBA")

def make_logo(text):
    S = 140; im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((4, 4, S - 4, S - 4), fill=YELLOW + (255,), outline=(255, 240, 160, 255), width=4)
    d.ellipse((12, 12, S - 12, S - 12), outline=(150, 100, 0, 120), width=2)
    t = text_img(text, 38, fill=(40, 28, 0), ar_path=AR_B); im.alpha_composite(t, ((S - t.width) // 2, (S - t.height) // 2))
    return im

# ---------- glossy static sprites (2x supersampled) ----------
def vgrad(w, h, c1, c2):
    t = np.linspace(0, 1, h, dtype="float32")[:, None, None]
    a = np.array(c1, "float32") * (1 - t) + np.array(c2, "float32") * t
    return Image.fromarray(np.broadcast_to(a, (h, w, 3)).astype("uint8")).convert("RGBA")
def rr_mask(w, h, r):
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255); return m
def gloss(w, h, r, alpha=70):
    g = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(g)
    d.polygon([(0, 0), (w * .62, 0), (w * .22, h), (0, h)], fill=(255, 255, 255, alpha))
    m = rr_mask(w, h, r); g.putalpha(Image.fromarray(np.minimum(np.array(g.split()[3]), np.array(m)))); return g
def bevel_box(w, h, r, c1, c2, border=(255, 255, 255, 60)):
    S = 2; W2, H2 = w * S, h * S; im = vgrad(W2, H2, c1, c2)
    im.putalpha(rr_mask(W2, H2, r * S)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, W2 - 3, H2 - 3), radius=r * S, outline=border, width=3 * S // 2)
    return im.resize((w, h), Image.LANCZOS)

def make_chip(text, border, fill=(255, 255, 255), txt=(20, 34, 70), size=44):
    t = text_img(text, size, fill=txt, ar_path=AR_B)
    im = Image.new("RGBA", (t.width + 70, t.height + 44), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((6, 10, im.width - 6, im.height - 2), radius=26, fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)))
    d.rounded_rectangle((4, 4, im.width - 8, im.height - 10), radius=26, fill=fill + (255,), outline=border + (255,), width=6)
    im.alpha_composite(t, ((im.width - 4 - t.width) // 2, (im.height - 6 - t.height) // 2)); return im

def make_sticker(text, kind="q"):
    col = {"q": (80, 120, 255), "ok": GREEN, "bad": RED}[kind]
    t = text_img(text, 52, fill=(18, 30, 64))
    h = max(t.height + 50, 112); w = t.width + 190
    im = Image.new("RGBA", (w + 20, h + 24), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((8, 14, w + 8, h + 12), radius=h // 2, fill=(0, 0, 0, 120))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d.rounded_rectangle((6, 6, w + 6, h + 2), radius=h // 2, fill=(252, 253, 255, 255), outline=col + (255,), width=6)
    cx, cy = w - h // 2 + 6, 4 + h // 2
    d.ellipse((cx - 36, cy - 36, cx + 36, cy + 36), fill=col + (255,))
    if kind == "ok": d.line((cx - 18, cy + 2, cx - 4, cy + 16, cx + 20, cy - 14), fill=(255, 255, 255, 255), width=10, joint="curve")
    elif kind == "bad": d.line((cx - 16, cy - 16, cx + 16, cy + 16), fill=(255, 255, 255, 255), width=10); d.line((cx - 16, cy + 16, cx + 16, cy - 16), fill=(255, 255, 255, 255), width=10)
    else:
        q = text_img("؟", 56, fill=(255, 255, 255)); im.alpha_composite(q, (cx - q.width // 2, cy - q.height // 2))
    im.alpha_composite(t, (30, 6 + (h - t.height) // 2)); return im

SHADOW = None
def shadow_sprite(w):
    global SHADOW
    s = Image.new("RGBA", (w + 120, 120), (0, 0, 0, 0)); ImageDraw.Draw(s).ellipse((60, 36, w + 60, 84), fill=(30, 12, 0, 150))
    return s.filter(ImageFilter.GaussianBlur(14))

def place(fr, sprite, cx, bottom, scale=1.0, shadow=True):
    if scale != 1.0: sprite = sprite.resize((max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))), Image.BILINEAR)
    x, y = int(cx - sprite.width / 2), int(bottom - sprite.height)
    if shadow:
        sh = shadow_sprite(int(sprite.width * .8)); fr.alpha_composite(sh, (int(cx - sh.width / 2), int(bottom - 70)))
    fr.alpha_composite(sprite, (x, y)); return x, y

def connector(fr, p0, p1, color, k):
    if k <= 0: return
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    x1 = p0[0] + (p1[0] - p0[0]) * k; y1 = p0[1] + (p1[1] - p0[1]) * k
    d.line((p0, (x1, y1)), fill=(255, 255, 255, 235), width=5); d.ellipse((x1 - 10, y1 - 10, x1 + 10, y1 + 10), fill=color + (255,), outline=(255, 255, 255, 255), width=3)
    fr.alpha_composite(L)

def pop_paste(fr, sprite, cx, cy, k):
    if k <= 0: return
    s = max(.05, ease_back(k, 1.8)); sp = sprite.resize((max(1, int(sprite.width * s)), max(1, int(sprite.height * s))), Image.BILINEAR)
    if k < 1: sp.putalpha(sp.split()[3].point(lambda v: int(v * min(1, k * 3))))
    fr.alpha_composite(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)))
