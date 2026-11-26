"""Object library: ~16 glossy 2.5D IT objects drawn locally with Pillow (no APIs, no assets).
Each OBJECTS[name](t, p) -> RGBA sprite, standing on its bottom edge. t = absolute seconds, p = seconds since the beat started."""
import math
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
from .core import *

_cache = {}
def cached(key, fn):
    if key not in _cache: _cache[key] = fn()
    return _cache[key]
def new(w, h): return Image.new("RGBA", (w, h), (0, 0, 0, 0))
def blur_glow(im, r=10, k=.7):
    return Image.blend(im, Image.alpha_composite(im, im.filter(ImageFilter.GaussianBlur(r))), k)
def label(im, text, cx, cy, size, fill=WHITE):
    t = text_img(text, size, fill=fill); im.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))
def feet(im, cx, w, y):
    im.alpha_composite(bevel_box(w, 34, 12, (70, 78, 96), (30, 34, 46)), (int(cx - w / 2), y))

# ---- TV / magnifier / panels (from the approved sample) ----
def tv(t, p):
    def mk():
        w, h = 620, 470; im = new(w, h); im.alpha_composite(bevel_box(600, 360, 26, (46, 52, 66), (18, 22, 32)), (10, 10))
        scr = vgrad(556, 316, (20, 40, 150), (180, 40, 120)); d = ImageDraw.Draw(scr)
        for i in range(7): d.ellipse((60 + i * 70, 60 + 25 * math.sin(i), 200 + i * 70, 220 + 25 * math.sin(i)), fill=[(255, 150, 40, 120), (60, 220, 200, 120), (255, 80, 140, 120), (120, 120, 255, 120)][i % 4])
        scr.putalpha(rr_mask(556, 316, 12)); scr.alpha_composite(gloss(556, 316, 12, 55)); im.alpha_composite(scr, (32, 32))
        ImageDraw.Draw(im).polygon([(250, 372), (370, 372), (400, 420), (220, 420)], fill=(40, 46, 60, 255)); feet(im, 310, 300, 424); return im
    return cached("tv", mk)

def pixel_color(t, c, r, k=0):
    v = .5 + .5 * math.sin(c * .6 + r * .5 - t * 3 + k)
    return (int(40 + 215 * v), int(120 + 100 * math.sin(c * .3 + t) ** 2), int(255 - 160 * v))

def magnifier(t, p):
    stand = cached("mag_stand", lambda: (lambda im: (ImageDraw.Draw(im).rectangle((262, 520, 298, 610), fill=(110, 80, 44, 255)), im.alpha_composite(bevel_box(300, 36, 14, (120, 90, 50), (70, 48, 24)), (130, 604)), im)[2])(new(560, 640))).copy()
    S = 560; inner = Image.new("RGBA", (S, S), (6, 8, 16, 255)); d = ImageDraw.Draw(inner)
    cols, rows, cw, chh = 5, 4, 96, 110; ox, oy = (S - cols * cw) // 2, (S - rows * chh) // 2
    for r in range(rows):
        for c in range(cols):
            lvl = .55 + .45 * math.sin(t * 3 + c * .9 + r * .7)
            for k, col in enumerate(((255, 60, 70), (70, 255, 110), (70, 140, 255))):
                x0 = ox + c * cw + 8 + k * 26; y0 = oy + r * chh + 8
                hh = int((chh - 20) * (.35 + .65 * lvl if k != 1 else .35 + .65 * (1 - lvl * .5)))
                d.rounded_rectangle((x0, y0 + (chh - 20 - hh), x0 + 22, y0 + chh - 20), radius=6, fill=col + (255,))
    inner = blur_glow(inner, 10, .8); m = Image.new("L", (S, S), 0); ImageDraw.Draw(m).ellipse((24, 24, S - 24, S - 24), fill=255)
    lens = new(S, S); lens.paste(inner, (0, 0), m); d = ImageDraw.Draw(lens)
    d.ellipse((12, 12, S - 12, S - 12), outline=(200, 150, 70, 255), width=24); d.ellipse((34, 34, S - 34, S - 34), outline=(255, 230, 170, 120), width=4)
    gs = new(S, S); ImageDraw.Draw(gs).pieslice((40, 40, S - 40, S - 40), 200, 260, fill=(255, 255, 255, 55)); lens.alpha_composite(gs)
    stand.alpha_composite(lens, (0, 0)); return stand.crop((0, 0, 560, 640))

def _panel(t, kind):
    w, h = 520, 440; im = new(w, h); im.alpha_composite(bevel_box(520, 340, 22, (52, 58, 74), (20, 24, 34)), (0, 0))
    scr = Image.new("RGBA", (480, 300), (2, 2, 4, 255) if kind == "oled" else (46, 58, 84, 255)); d = ImageDraw.Draw(scr)
    for r in range(8):
        for c in range(12):
            if kind == "oled":
                if (c + r) % 5 == 0: continue
                col = pixel_color(t, c, r)
            else: col = tuple(int(x * .75 + 40) for x in pixel_color(t, c, r))
            x0, y0 = 20 + c * 37, 20 + r * 33; d.rounded_rectangle((x0, y0, x0 + 26, y0 + 22), radius=6, fill=col + (255,))
    if kind == "oled": scr = blur_glow(scr, 9, 1.0)
    scr.putalpha(rr_mask(480, 300, 10)); scr.alpha_composite(gloss(480, 300, 10, 40)); im.alpha_composite(scr, (20, 20))
    ImageDraw.Draw(im).polygon([(220, 340), (300, 340), (322, 392), (198, 392)], fill=(40, 46, 60, 255)); feet(im, 260, 240, 396); return im
def oled(t, p): return _panel(t, "oled")
def qled(t, p): return _panel(t, "qled")

def pixels(t, p, t_off=1.8):
    S = 460; im = bevel_box(S, S, 28, (52, 58, 74), (20, 24, 34)); inner = Image.new("RGBA", (S - 40, S - 40), (2, 2, 4, 255)); d = ImageDraw.Draw(inner)
    n = 6; cs = (S - 40) // n
    for r in range(n):
        for c in range(n):
            off_at = t_off + (r * n + c) * .045; lvl = 1.0 if p < off_at else max(0.0, 1 - (p - off_at) / .18)
            if lvl <= 0: continue
            col = tuple(int(x * lvl) for x in pixel_color(t, c, r)); x0, y0 = c * cs + 12, r * cs + 12
            d.rounded_rectangle((x0, y0, x0 + cs - 24, y0 + cs - 24), radius=12, fill=col + (255,))
    inner = blur_glow(inner, 12, 1.0); inner.putalpha(rr_mask(S - 40, S - 40, 14)); inner.alpha_composite(gloss(S - 40, S - 40, 14, 38)); im.alpha_composite(inner, (20, 20))
    full = new(S, S + 40); full.alpha_composite(im, (0, 0)); feet(full, S / 2, 200, S + 4); return full

# ---- new objects ----
def cpu(t, p):
    def mk():
        S = 520; im = new(S, S); d = ImageDraw.Draw(im)
        im.alpha_composite(bevel_box(440, 440, 30, (40, 140, 90), (16, 78, 54)), (40, 40))
        for i in range(12):
            x = 78 + i * 32
            for y0 in (14, 466): d.rounded_rectangle((x, y0, x + 14, y0 + 40), radius=4, fill=(236, 190, 90, 255))
            for xx in (14, 466): d.rounded_rectangle((xx, x, xx + 40, x + 14), radius=4, fill=(236, 190, 90, 255))
        im.alpha_composite(bevel_box(300, 300, 22, (200, 206, 216), (120, 128, 142), border=(255, 255, 255, 140)), (110, 110))
        im.alpha_composite(bevel_box(230, 230, 16, (60, 66, 82), (24, 28, 40)), (145, 145)); label(im, "CPU", 260, 262, 64, (120, 220, 255)); return im
    im = cached("cpu", lambda: mk()).copy(); g = glow(150, CYAN, int(70 + 40 * math.sin(t * 4)), 1.8); im.alpha_composite(g, (110, 110)); return im

def gpu(t, p):
    def mk():
        w, h = 640, 340; im = new(w, h); im.alpha_composite(bevel_box(620, 250, 26, (44, 50, 64), (16, 20, 30)), (10, 10))
        im.alpha_composite(bevel_box(600, 26, 8, (236, 190, 90), (180, 130, 40)), (20, 262))
        ImageDraw.Draw(im).rectangle((90, 262, 130, 288), fill=(20, 24, 34, 255)); ImageDraw.Draw(im).rectangle((420, 262, 440, 288), fill=(20, 24, 34, 255))
        ImageDraw.Draw(im).rectangle((30, 250, 80, 330), fill=(70, 78, 96, 255)); ImageDraw.Draw(im).rectangle((560, 250, 610, 330), fill=(70, 78, 96, 255))
        label(im, "GPU", 320, 236, 40, (120, 220, 255)); return im
    im = cached("gpu", mk).copy(); d = ImageDraw.Draw(im)
    for cx in (190, 450):
        d.ellipse((cx - 98, 32, cx + 98, 228), fill=(14, 18, 28, 255), outline=(90, 100, 120, 255), width=5)
        for k in range(7):
            a = t * 9 + k * 2 * math.pi / 7; d.polygon([(cx, 130), (cx + 88 * math.cos(a - .2), 130 + 88 * math.sin(a - .2)), (cx + 88 * math.cos(a + .35), 130 + 88 * math.sin(a + .35))], fill=(150, 180, 220, 255))
        d.ellipse((cx - 22, 108, cx + 22, 152), fill=(30, 36, 50, 255), outline=CYAN + (255,), width=4)
    return im

def phone(t, p):
    def mk():
        w, h = 320, 600; im = new(w, h); im.alpha_composite(bevel_box(300, 580, 48, (62, 70, 90), (14, 18, 28), border=(255, 255, 255, 110)), (10, 10))
        scr = vgrad(268, 530, (30, 70, 190), (150, 50, 170)); d = ImageDraw.Draw(scr)
        for i in range(12):
            x, y = 22 + (i % 3) * 82, 70 + (i // 3) * 92; d.rounded_rectangle((x, y, x + 62, y + 62), radius=16, fill=[(255, 200, 60, 230), (70, 220, 160, 230), (255, 100, 120, 230), (255, 255, 255, 220)][(i + i // 3) % 4])
        d.rounded_rectangle((84, 14, 184, 40), radius=13, fill=(8, 10, 16, 255))
        scr.putalpha(rr_mask(268, 530, 36)); scr.alpha_composite(gloss(268, 530, 36, 50)); im.alpha_composite(scr, (26, 35)); return im
    return cached("phone", mk)

def router(t, p):
    def mk():
        w, h = 620, 560; im = new(w, h); d = ImageDraw.Draw(im)
        for x in (110, 310, 510): im.alpha_composite(bevel_box(26, 300, 10, (60, 66, 84), (22, 26, 38)), (x - 13 if x != 310 else x - 13, 190 - 20 + 20))
        im.alpha_composite(bevel_box(560, 130, 26, (230, 234, 244), (150, 158, 176), border=(255, 255, 255, 160)), (30, 420)); return im
    im = cached("router", mk).copy(); d = ImageDraw.Draw(im)
    for i in range(4):
        on = math.sin(t * 6 + i * 1.7) > -.2; d.ellipse((90 + i * 40, 474, 108 + i * 40, 492), fill=((60, 230, 120) if on else (40, 70, 52)) + (255,))
    for k in range(3):
        ph = (t * 1.2 + k / 3) % 1; r = 40 + ph * 190; a = int(220 * (1 - ph))
        for dx in (0,):
            d.arc((310 - r, 200 - r, 310 + r, 200 + r), 225, 315, fill=CYAN + (a,), width=10)
    return im

def battery(t, p):
    def mk():
        w, h = 380, 600; im = new(w, h); im.alpha_composite(bevel_box(130, 50, 14, (160, 168, 184), (100, 108, 124)), (125, 0))
        im.alpha_composite(bevel_box(340, 530, 40, (60, 68, 86), (18, 22, 34), border=(255, 255, 255, 120)), (20, 50)); return im
    im = cached("battery", mk).copy(); d = ImageDraw.Draw(im); lvl = .25 + .7 * ((t * .35) % 1)
    top = 90 + int((1 - lvl) * 420); col = (60, 220, 110) if lvl > .45 else (250, 190, 40)
    d.rounded_rectangle((50, top, 330, 560), radius=22, fill=col + (255,))
    d.polygon([(205, 190), (140, 330), (190, 330), (165, 450), (250, 290), (200, 290), (225, 190)], fill=(255, 255, 255, 235))
    return im

def cloud(t, p):
    im = new(620, 440); bob = int(8 * math.sin(t * 2)); d = ImageDraw.Draw(im)
    for (x, y, r) in ((200, 250, 110), (320, 190, 140), (450, 250, 105), (300, 290, 120), (400, 300, 100)): d.ellipse((x - r, y - r + bob, x + r, y + r + bob), fill=(235, 244, 255, 255))
    d.rounded_rectangle((120, 270 + bob, 520, 380 + bob), radius=54, fill=(235, 244, 255, 255))
    d.rounded_rectangle((120, 340 + bob, 520, 380 + bob), radius=20, fill=(190, 210, 240, 255))
    ph = (t * .9) % 1; ay = 330 - ph * 110 + bob; a = int(255 * min(1, 3 * (1 - ph)))
    d.polygon([(310, ay - 70), (250, ay), (290, ay), (290, ay + 60), (330, ay + 60), (330, ay), (370, ay)], fill=(60, 120, 230, a))
    return im

def lock(t, p):
    def mk():
        w, h = 440, 560; im = new(w, h); d = ImageDraw.Draw(im)
        d.arc((90, 20, 350, 330), 180, 360, fill=(190, 196, 210, 255), width=42); d.rectangle((90, 170, 132, 270), fill=(190, 196, 210, 255)); d.rectangle((308, 170, 350, 270), fill=(190, 196, 210, 255))
        im.alpha_composite(bevel_box(400, 300, 44, (252, 206, 80), (196, 130, 30), border=(255, 255, 255, 150)), (20, 240))
        d.ellipse((190, 330, 250, 390), fill=(60, 36, 8, 255)); d.polygon([(210, 380), (230, 380), (240, 470), (200, 470)], fill=(60, 36, 8, 255)); return im
    return cached("lock", mk)

def camera(t, p):
    def mk():
        w, h = 620, 470; im = new(w, h); d = ImageDraw.Draw(im)
        im.alpha_composite(bevel_box(600, 380, 40, (70, 76, 92), (22, 26, 38), border=(255, 255, 255, 110)), (10, 70))
        im.alpha_composite(bevel_box(200, 60, 16, (90, 98, 116), (40, 44, 58)), (60, 22)); d.rounded_rectangle((470, 90, 560, 130), radius=10, fill=(255, 245, 200, 255))
        for r, c in ((150, (20, 22, 30)), (126, (60, 66, 84)), (100, (14, 18, 40)), (66, (40, 90, 200)), (30, (140, 190, 255))): d.ellipse((310 - r, 275 - r, 310 + r, 275 + r), fill=c + (255,))
        d.pieslice((240, 205, 380, 345), 200, 250, fill=(255, 255, 255, 110)); return im
    return cached("camera", mk)

def ssd(t, p):
    def mk():
        w, h = 620, 330; im = new(w, h); d = ImageDraw.Draw(im)
        im.alpha_composite(bevel_box(600, 260, 30, (60, 66, 84), (20, 24, 34), border=(255, 255, 255, 110)), (10, 10))
        im.alpha_composite(bevel_box(300, 120, 14, (210, 216, 228), (150, 158, 174)), (40, 40)); label(im, "SSD", 190, 100, 54, (20, 34, 70))
        for i in range(3): d.rounded_rectangle((380 + i * 70, 50, 440 + i * 70, 120), radius=8, fill=(14, 16, 24, 255), outline=(90, 100, 120, 255), width=3)
        d.rectangle((60, 190, 560, 240), fill=(40, 46, 60, 255)); im.alpha_composite(bevel_box(480, 30, 6, (236, 190, 90), (180, 130, 40)), (70, 272)); return im
    im = cached("ssd", mk).copy(); a = int(120 + 120 * (math.sin(t * 8) > 0)); ImageDraw.Draw(im).ellipse((540, 30, 560, 50), fill=(60, 230, 120, a)); return im

def signal(t, p):
    im = new(560, 560); d = ImageDraw.Draw(im)
    d.polygon([(250, 540), (310, 540), (290, 250), (270, 250)], fill=(90, 100, 124, 255)); d.polygon([(220, 540), (340, 540), (330, 520), (230, 520)], fill=(60, 68, 86, 255))
    d.ellipse((248, 215, 312, 279), fill=(240, 100, 100, 255), outline=(255, 255, 255, 255), width=4)
    for k in range(4):
        ph = (t * .9 + k / 4) % 1; r = 40 + ph * 230; a = int(255 * (1 - ph))
        d.arc((280 - r, 247 - r, 280 + r, 247 + r), 200, 340, fill=CYAN + (a,), width=12); d.arc((280 - r, 247 - r, 280 + r, 247 + r), 20, 160, fill=CYAN + (a,), width=12)
    return im

def ram(t, p):
    def mk():
        w, h = 660, 250; im = new(w, h); d = ImageDraw.Draw(im)
        im.alpha_composite(bevel_box(640, 190, 14, (40, 140, 90), (16, 78, 54)), (10, 10))
        for i in range(8): im.alpha_composite(bevel_box(62, 80, 8, (50, 54, 66), (16, 18, 26)), (50 + i * 72, 40))
        label(im, "RAM", 330, 150, 46, WHITE)
        for i in range(24):
            if abs(i - 11.5) > 1: d.rectangle((24 + i * 25, 200, 40 + i * 25, 240), fill=(236, 190, 90, 255))
        return im
    return cached("ram", mk)

OBJECTS = {"tv": tv, "magnifier": magnifier, "oled": oled, "qled": qled, "pixels": pixels, "cpu": cpu, "gpu": gpu, "phone": phone,
           "router": router, "battery": battery, "cloud": cloud, "lock": lock, "camera": camera, "ssd": ssd, "signal": signal, "ram": ram}
