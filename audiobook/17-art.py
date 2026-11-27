import random,numpy as np,json,arabic_reshaper
from PIL import Image,ImageDraw,ImageFilter,ImageFont
import subprocess,glob
def _font(black):
    for p in glob.glob('/usr/share/fonts/**/NotoKufiArabic-%s.ttf'%('Black' if black else 'Regular'),recursive=True): return p
    for p in glob.glob('/usr/share/fonts/**/NotoSansArabic-Bold.ttf',recursive=True)+glob.glob('/usr/share/fonts/**/NotoSansArabic[[]*.ttf',recursive=True): return p
    return subprocess.check_output(['fc-match','-f','%{file}',':lang=ar']).decode()
FB=_font(True);FR=_font(False)
from bidi.algorithm import get_display
W,H=1600,900
PAL=[((10,14,30),(70,40,60),(255,190,110)),((8,20,28),(30,60,80),(240,220,160)),((20,10,14),(80,30,30),(255,150,90)),((12,12,20),(50,50,90),(200,210,255)),((18,16,10),(70,60,35),(255,210,120))]
def bg(seed,idx):
    r=random.Random(seed);top,bot,glow=PAL[idx%len(PAL)]
    y=np.linspace(0,1,H)[:,None,None]
    a=np.array(top)[None,None,:]*(1-y)+np.array(bot)[None,None,:]*y
    a=np.repeat(a,W,1)
    im=Image.fromarray(a.astype('uint8'))
    d=ImageDraw.Draw(im,'RGBA')
    # glow orb (moon / lamp)
    ox,oy=r.randint(300,1300),r.randint(120,330);R=r.randint(50,90)
    g=Image.new('RGBA',(W,H),(0,0,0,0));gd=ImageDraw.Draw(g)
    for k in range(8,0,-1): gd.ellipse([ox-R*k/2,oy-R*k/2,ox+R*k/2,oy+R*k/2],fill=glow+(14,))
    gd.ellipse([ox-R/2,oy-R/2,ox+R/2,oy+R/2],fill=glow+(230,))
    im=Image.alpha_composite(im.convert('RGBA'),g.filter(ImageFilter.GaussianBlur(25)))
    d=ImageDraw.Draw(im,'RGBA')
    # layered skyline
    for layer in range(3):
        base=H-60-layer*0; col=tuple(int(c*(0.25-layer*0.07)) for c in bot)+(255,)
        x=-20;hmax=[330,250,170][layer]
        while x<W:
            w=r.randint(60,150);h=r.randint(hmax//3,hmax)+layer*0
            top_y=H-h-(2-layer)*40
            d.rectangle([x,top_y,x+w,H],fill=tuple(int(c*(0.55-layer*0.17)) for c in bot)+(255,))
            if layer<2:
                for wx in range(x+10,x+w-10,22):
                    for wy in range(top_y+14,H-30,30):
                        if r.random()<0.22: d.rectangle([wx,wy,wx+8,wy+12],fill=glow+(r.randint(90,200),))
            x+=w+r.randint(0,10)
    # fog
    n=np.random.RandomState(seed).rand(H//30,W//30)
    f=Image.fromarray((n*255).astype('uint8')).resize((W,H),Image.BICUBIC).filter(ImageFilter.GaussianBlur(40))
    fog=Image.new('RGBA',(W,H),(200,200,210,0));fog.putalpha(f.point(lambda v:int(v*0.18)))
    im=Image.alpha_composite(im,fog)
    # vignette
    yy,xx=np.mgrid[0:H,0:W];v=1-0.55*(((xx-W/2)/(W/2))**2+((yy-H/2)/(H/2))**2)/2
    arr=np.array(im.convert('RGB')).astype(float)*np.clip(v,0.3,1)[:,:,None]
    return Image.fromarray(arr.astype('uint8'))
def ar(t): return t
def title_card(im,line1,line2=None,size=96):
    d=ImageDraw.Draw(im,'RGBA');d.rectangle([0,0,W,H],fill=(0,0,0,110))
    f=ImageFont.truetype(FB,size)
    d.text((W/2,H/2-20),ar(line1),font=f,fill=(255,255,255),anchor='mm',direction='rtl',language='ar',stroke_width=3,stroke_fill=(0,0,0))
    if line2:
        f2=ImageFont.truetype(FR,44)
        d.text((W/2,H/2+90),ar(line2),font=f2,fill=(255,200,120),anchor='mm',direction='rtl',language='ar')
    return im
def thumb(t1='التهمة',l1='اتسجن 4 سنين',l2='وهو نايم في بيته',sub='البارت 1   رواية عربية مسموعة',out='thumbnail.jpg',theme=None):
    if theme:
        from scenes import SC
        im=SC[theme](7).resize((1280,720)).convert('RGB');d=ImageDraw.Draw(im,'RGBA')
        d.rectangle([0,0,1280,720],fill=(0,0,0,20));d.rectangle([0,0,800,720],fill=(0,0,0,50))
    else:
        im=bg(7,2).resize((1280,720));d=ImageDraw.Draw(im,'RGBA')
        # bars + figure
        d.rectangle([0,0,1280,720],fill=(0,0,0,60))
        for x in range(760,1240,60): d.rectangle([x,0,x+10,720],fill=(10,10,10,235))
        d.ellipse([930,300,1030,400],fill=(8,8,8,255))
        d.rounded_rectangle([890,400,1070,720],40,fill=(8,8,8,255))
    sz=190
    while sz>70 and d.textlength(ar(t1),font=ImageFont.truetype(FB,sz),direction='rtl',language='ar')>740: sz-=6
    f=ImageFont.truetype(FB,sz)
    d.text((400,250),ar(t1),font=f,fill=(255,215,60),anchor='mm',direction='rtl',language='ar',stroke_width=8,stroke_fill=(0,0,0))
    f2=ImageFont.truetype(FB,62)
    d.text((400,420),ar(l1),font=f2,fill=(255,255,255),anchor='mm',direction='rtl',language='ar',stroke_width=5,stroke_fill=(0,0,0))
    d.text((400,500),ar(l2),font=f2,fill=(255,255,255),anchor='mm',direction='rtl',language='ar',stroke_width=5,stroke_fill=(0,0,0))
    f3=ImageFont.truetype(FR,44)
    d.text((400,620),ar(sub),font=f3,fill=(255,150,90),anchor='mm',direction='rtl',language='ar',stroke_width=3,stroke_fill=(0,0,0))
    im.convert('RGB').save(out,quality=92)
if __name__=='__main__':
    thumb()
