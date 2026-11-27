import random,numpy as np
from PIL import Image,ImageDraw,ImageFilter
from art import W,H,bg
def finish(im,seed):
    r=np.random.RandomState(seed);n=r.rand(H//40,W//40)
    f=Image.fromarray((n*255).astype('uint8')).resize((W,H),Image.BICUBIC).filter(ImageFilter.GaussianBlur(50))
    im=im.convert('RGBA');fog=Image.new('RGBA',(W,H),(220,220,230,0));fog.putalpha(f.point(lambda v:int(v*0.10)))
    im=Image.alpha_composite(im,fog).convert('RGB')
    yy,xx=np.mgrid[0:H,0:W];v=np.clip(1-0.5*(((xx-W/2)/(W/2))**2+((yy-H/2)/(H/2))**2)/2,0.3,1)
    return Image.fromarray((np.array(im).astype(float)*v[:,:,None]).astype('uint8'))
def grad(top,bot):
    y=np.linspace(0,1,H)[:,None,None];a=np.array(top)[None,None,:]*(1-y)+np.array(bot)[None,None,:]*y
    return Image.fromarray(np.repeat(a,W,1).astype('uint8'))
def glow(im,x,y,R,col,a=60):
    g=Image.new('RGBA',im.size,(0,0,0,0));d=ImageDraw.Draw(g)
    for k in range(10,0,-1): d.ellipse([x-R*k/3,y-R*k/3,x+R*k/3,y+R*k/3],fill=col+(a//4,))
    return Image.alpha_composite(im.convert('RGBA'),g.filter(ImageFilter.GaussianBlur(30))).convert('RGB')
def person(d,x,base,h,col=(8,8,10,255)):
    d.ellipse([x-h*.1,base-h,x+h*.1,base-h*.8],fill=col);d.rounded_rectangle([x-h*.16,base-h*.8,x+h*.16,base-h*.35],14,fill=col)
    d.rectangle([x-h*.14,base-h*.35,x+h*.14,base],fill=col)
def shop(s):
    r=random.Random(s);im=grad((30,24,22),(55,42,34));d=ImageDraw.Draw(im,'RGBA')
    d.rectangle([0,640,W,H],fill=(40,30,25));d.rectangle([0,0,W,640],fill=(70,58,48))
    for i in range(5): d.rectangle([60+i*150,120,190+i*150,160],fill=(35,30,28)) if False else None
    d.rectangle([80,150,780,170],fill=(30,24,20));d.rectangle([80,300,780,320],fill=(30,24,20))
    for row in (150,300):
        for x in range(100,760,60):
            if r.random()<.8: d.rounded_rectangle([x,row-70+ (0),x+36,row],4,fill=(r.randint(20,60),r.randint(20,60),r.randint(30,80),255))
    d.rectangle([880,420,1500,470],fill=(24,18,14));d.rectangle([880,470,1500,H],fill=(32,24,18))  # counter
    d.rectangle([1100,330,1300,420],fill=(15,15,20));d.rectangle([1110,340,1290,410],fill=(60,120,160,200))  # screen
    d.rectangle([1000,150,1400,170],fill=(255,200,100,230)) 
    im=glow(im,1200,160,60,(255,210,130),90);d=ImageDraw.Draw(im,'RGBA')
    person(d,1000,430,300)
    d.rectangle([160,500,330,640],fill=(25,20,18));d.rectangle([180,520,310,560],fill=(255,200,110,120))
    return finish(im,s)
def police(s):
    im=grad((22,28,34),(40,48,52));d=ImageDraw.Draw(im,'RGBA')
    d.rectangle([0,650,W,H],fill=(30,34,36))
    d.rectangle([150,150,500,420],fill=(210,220,200,60));d.rectangle([150,150,500,420],outline=(15,15,15,255),width=10)
    d.line([325,150,325,420],fill=(15,15,15,255),width=8)
    d.rectangle([700,520,1450,560],fill=(26,20,14));d.rectangle([740,560,780,680],fill=(26,20,14));d.rectangle([1370,560,1410,680],fill=(26,20,14))
    d.polygon([(960,420),(1200,400),(1230,520),(950,520)],fill=(200,200,180,90))
    im=glow(im,1050,300,60,(230,240,255),110);d=ImageDraw.Draw(im,'RGBA')
    d.rectangle([1040,300,1060,430],fill=(10,10,10,255));d.polygon([(960,300),(1140,300),(1100,260),(1000,260)],fill=(20,20,20,255))
    person(d,1500,700,380);person(d,620,700,330)
    return finish(im,s)
def court(s):
    im=grad((26,18,12),(60,40,26));d=ImageDraw.Draw(im,'RGBA')
    d.rectangle([0,680,W,H],fill=(34,22,14))
    for x in range(100,W,260): d.rectangle([x,0,x+50,680],fill=(52,34,22,255))
    d.rectangle([450,360,1150,470],fill=(40,25,15,255));d.rectangle([420,330,1180,365],fill=(55,34,20,255))
    d.rectangle([720,200,880,260],fill=(150,125,70,255))
    im=glow(im,800,120,80,(255,215,140),120);d=ImageDraw.Draw(im,'RGBA')
    person(d,800,360,200)
    for x in range(200,1400,220):
        d.rectangle([x,640,x+170,700],fill=(30,20,12,255));d.rectangle([x,600,x+170,640],fill=(40,28,18,255))
    person(d,1400,700,320)
    d.line([780,480,820,480],fill=(180,150,90,255),width=3)
    return finish(im,s)
def jail(s):
    im=grad((14,16,22),(30,34,40));d=ImageDraw.Draw(im,'RGBA')
    d.rectangle([0,700,W,H],fill=(22,24,26));d.rectangle([1000,380,1500,440],fill=(40,42,46))
    d.rectangle([1050,440,1450,700],fill=(34,36,40));d.rectangle([1100,330,1380,380],fill=(60,60,70))
    im=glow(im,300,160,70,(200,220,255),110);d=ImageDraw.Draw(im,'RGBA')
    d.rectangle([230,100,370,240],fill=(190,210,230,200))
    for x in range(260,350,30): d.rectangle([x,100,x+6,240],fill=(10,10,10,255))
    person(d,640,700,300)
    for x in range(0,W,95): d.rectangle([x,0,x+16,H],fill=(6,6,8,255))
    d.rectangle([0,60,W,76],fill=(6,6,8,255));d.rectangle([0,760,W,776],fill=(6,6,8,255))
    return finish(im,s)
def street(s):
    r=random.Random(s);im=bg(s,s%5);d=ImageDraw.Draw(im,'RGBA')
    d.rectangle([0,760,W,H],fill=(18,18,20));d.rectangle([0,740,W,765],fill=(40,40,44))
    for x in (300,900,1450):
        d.rectangle([x,380,x+14,760],fill=(8,8,8,255))
    im=glow(im,307,380,50,(255,210,120),120);im=glow(im,907,380,50,(255,210,120),120);d=ImageDraw.Draw(im,'RGBA')
    person(d,r.randint(500,800),770,260);person(d,r.randint(1000,1300),770,300)
    return finish(im,s)
def home(s):
    im=grad((26,20,26),(48,36,40));d=ImageDraw.Draw(im,'RGBA')
    d.rectangle([0,700,W,H],fill=(32,24,22))
    d.rectangle([1000,150,1400,500],fill=(120,150,190,90));d.rectangle([1000,150,1400,500],outline=(12,12,12,255),width=12)
    d.line([1200,150,1200,500],fill=(12,12,12,255),width=8);d.line([1000,325,1400,325],fill=(12,12,12,255),width=8)
    d.rectangle([150,480,650,700],fill=(40,28,26,255));d.rectangle([150,420,650,490],fill=(60,40,38,255))
    d.rectangle([700,560,900,700],fill=(36,26,22));d.rectangle([720,500,880,560],fill=(255,200,110,90))
    im=glow(im,800,450,50,(255,200,110),140);d=ImageDraw.Draw(im,'RGBA')
    person(d,1150,720,360)
    return finish(im,s)
SC={'shop':shop,'police':police,'court':court,'jail':jail,'street':street,'home':home}
if __name__=='__main__':
    for k,f in SC.items(): f(3).resize((640,360)).save(f'/tmp/v2/t_{k}.png')
    ims=[Image.open(f'/tmp/v2/t_{k}.png') for k in SC]
    sheet=Image.new('RGB',(1920,720))
    for i,im in enumerate(ims): sheet.paste(im,((i%3)*640,(i//3)*360))
    sheet.save('/downloads/scenes_sheet.png')
