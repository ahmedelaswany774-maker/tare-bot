"""Build a long audio-novel video from a story text (edge-tts + generated scenes + ffmpeg) and upload it to YouTube.
Usage: python audiobook/make_video.py audiobook/<story>.json   Env: YT_TOKEN_JSON, PRIVACY (default public), DRY_RUN (true/false), RATE (default +10%)."""
import re,asyncio,glob,json,os,random,subprocess,sys,time,urllib.request,re
import edge_tts
sys.path.insert(0,os.path.dirname(__file__))
from art import bg,title_card,thumb
from scenes import SC
cfg=json.load(open(sys.argv[1]));W='work';os.makedirs(W+'/ch',exist_ok=True)
VOICE='ar-EG-ShakirNeural';RATE=os.getenv('RATE','+10%');BACKEND=os.getenv('TTS_BACKEND','fish')
import requests
lines=[l.strip() for l in open(cfg['script'],encoding='utf-8').read().split('\n')[3:] if l.strip()]
chs=[];cur=None
for l in lines:
    if l.startswith('الفصل '): cur=[l.split(':',1)[1].strip(),[]];chs.append(cur)
    elif cur: cur[1].append(l)
print('chapters',len(chs),'words',sum(len(p.split()) for c in chs for p in c[1]))
def fish_one(txt,out):
    h={'Authorization':'Bearer '+os.environ['FISH_API_KEY'],'Content-Type':'application/json','model':'s2.1-pro-free'}
    for i in range(8):
        try:
            r=requests.post('https://api.fish.audio/v1/tts',headers=h,json={'text':txt,'reference_id':os.environ['FISH_VOICE_ID'],'format':'mp3'},timeout=180)
            r.raise_for_status();open(out,'wb').write(r.content)
            if os.path.getsize(out)>500: return
        except Exception as e: print('fish retry',i,str(e)[:100])
        time.sleep(3+3*i)
    raise SystemExit('fish tts failed '+out)
def pieces(t):
    # keep each request under ~700 chars, split at sentence ends (Fish never gets a different voice substituted)
    out=[];cur=''
    for s in re.split(r'(?<=[.!؟?…])\s+',t):
        if cur and len(cur)+len(s)>700: out.append(cur);cur=s
        else: cur=(cur+' '+s).strip()
    if cur: out.append(cur)
    return out
async def one(txt,out):
    if BACKEND=='fish':
        await asyncio.get_event_loop().run_in_executor(None,fish_one,txt,out);return
    for i in range(6):
        try:
            await edge_tts.Communicate(txt,VOICE,rate=RATE).save(out)
            if os.path.getsize(out)>500: return
        except Exception as e: print('retry',e)
        await asyncio.sleep(2+i)
    raise SystemExit('tts failed '+out)
async def tts():
    sem=asyncio.Semaphore(2 if BACKEND=='fish' else 8)
    async def job(ci,pi,t):
        o=f'{W}/a_{ci:02d}_{pi:03d}.mp3'
        if os.path.exists(o) and os.path.getsize(o)>500: return
        async with sem: await one(t,o)
    jobs=[];
    for ci,(t,ps) in enumerate(chs):
        items=[t+'.']+[x for p in ps for x in pieces(p)]
        jobs+= [job(ci,pi,p) for pi,p in enumerate(items)]
    await asyncio.gather(*jobs)
asyncio.run(tts())
def dur(f): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f]))
def run(a): subprocess.run(a,check=True)
mains=cfg['mains']
for ci,(t,_) in enumerate(chs):
    out=f'{W}/ch/c{ci:02d}.mp4'
    fs=sorted(glob.glob(f'{W}/a_{ci:02d}_*.mp3'))
    open(f'{W}/l{ci}.txt','w').write(''.join(f"file '{os.path.abspath(f)}'\n" for f in fs))
    run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',f'{W}/l{ci}.txt','-ar','44100','-ac','1',f'{W}/ch/a{ci:02d}.wav'])
    D=dur(f'{W}/ch/a{ci:02d}.wav');n=max(1,round(D/22));seg=D/n;parts=[]
    for k in range(n):
        im=SC[(mains[ci%len(mains)] if k%3!=2 else 'street')](ci*100+k)
        if k==0: im=title_card(im,t,f'الفصل {ci+1}')
        im.save(f'{W}/s.png')
        z=random.Random(ci*7+k).choice([('min(zoom+0.0006,1.25)','iw/2-(iw/zoom/2)','ih/2-(ih/zoom/2)'),('1.2-0.0006*on','(iw-iw/zoom)*on/%d'%(seg*20),'ih/2-(ih/zoom/2)'),('1.15','(iw-iw/zoom)*(1-on/%d)'%(seg*20),'(ih-ih/zoom)*on/%d'%(seg*20))])
        p=f'{W}/ch/p{ci:02d}_{k:03d}.mp4';parts.append(p)
        run(['ffmpeg','-y','-loglevel','error','-loop','1','-i',f'{W}/s.png','-vf',f"zoompan=z='{z[0]}':x='{z[1]}':y='{z[2]}':d={int(seg*20)+1}:s=1280x720:fps=20,fade=t=in:d=0.6",'-t',f'{seg:.2f}','-c:v','libx264','-preset','ultrafast','-crf','24','-pix_fmt','yuv420p',p])
    open(f'{W}/v{ci}.txt','w').write(''.join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',f'{W}/v{ci}.txt','-i',f'{W}/ch/a{ci:02d}.wav','-c:v','copy','-c:a','aac','-b:a','96k','-shortest',out])
    for p in parts: os.remove(p)
    print('chapter',ci,round(D))
open(f'{W}/all.txt','w').write(''.join(f"file '{os.path.abspath(f)}'\n" for f in sorted(glob.glob(f'{W}/ch/c*.mp4'))))
final=f"{W}/{cfg['slug']}.mp4";run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',f'{W}/all.txt','-c','copy',final])
th=cfg['thumb'];thumb(th['t1'],th['l1'],th['l2'],th['sub'],f'{W}/thumb.jpg')
total=dur(final);print('final',final,round(total/60,1),'min',os.path.getsize(final)>>20,'MB')
if os.getenv('DRY_RUN','false').lower()=='true': sys.exit(0)
# --- upload ---
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
creds=Credentials.from_authorized_user_info(json.loads(os.environ['YT_TOKEN_JSON']))
if not creds.valid: creds.refresh(Request())
yt=build('youtube','v3',credentials=creds)
ch=yt.channels().list(part='id,snippet',mine=True).execute()['items'][0]
print('uploading to channel:',ch['snippet']['title'],ch['id'])
# exact-title dedup: public RSS feed (15 newest) + uploads playlist when the token allows it
norm=lambda s:re.sub(r'\s+',' ',s).strip()
feed=urllib.request.urlopen('https://www.youtube.com/feeds/videos.xml?channel_id='+ch['id']).read().decode()
titles=set(norm(x) for x in re.findall(r'<media:title>(.*?)</media:title>',feed))
try:
    pl=yt.channels().list(part='contentDetails',mine=True).execute()['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    tok=None
    while True:
        r=yt.playlistItems().list(part='snippet',playlistId=pl,maxResults=50,pageToken=tok).execute()
        titles|=set(norm(i['snippet']['title']) for i in r['items']);tok=r.get('nextPageToken')
        if not tok: break
except Exception as e: print('playlist dedup unavailable:',str(e)[:120])
if norm(cfg['title']) in titles: raise SystemExit('DUPLICATE TITLE on channel, not uploading')
body={'snippet':{'title':cfg['title'],'description':cfg['description'],'tags':cfg['tags'],'categoryId':'24','defaultLanguage':'ar','defaultAudioLanguage':'ar'},
 'status':{'privacyStatus':os.getenv('PRIVACY','public'),'selfDeclaredMadeForKids':False,'containsSyntheticMedia':True}}
req=yt.videos().insert(part='snippet,status',body=body,media_body=MediaFileUpload(final,chunksize=32*1024*1024,resumable=True))
resp=None
while resp is None:
    st,resp=req.next_chunk()
    if st: print('upload',int(st.progress()*100),'%')
vid=resp['id'];print('VIDEO_ID',vid,'https://www.youtube.com/watch?v='+vid)
try: yt.thumbnails().set(videoId=vid,media_body=MediaFileUpload(f'{W}/thumb.jpg')).execute();print('thumbnail set')
except Exception as e: print('thumbnail failed:',str(e)[:200])
