"""Make a ~3 minute voice sample of a story opening with the channel's Fish voice, for review. Writes audiobook/samples/<slug>_fish.mp3"""
import json,os,re,sys,requests,subprocess
cfg=json.load(open(sys.argv[1]));os.makedirs('audiobook/samples',exist_ok=True)
L=[l.strip() for l in open(cfg['script'],encoding='utf-8').read().split('\n')[3:] if l.strip()]
paras=[l for l in L if not l.startswith('الفصل ')]
txt=' '.join(paras);cur='';pieces=[]
for s in re.split(r'(?<=[.!؟?…])\s+',txt):
    if cur and len(cur)+len(s)>600: pieces.append(cur);cur=s
    else: cur=(cur+' '+s).strip()
    if len(pieces)>=3: break
pieces=pieces[:3]
H={'Authorization':'Bearer '+os.environ['FISH_API_KEY']}
try:
    b=requests.get('https://api.fish.audio/wallet/self/api-credit',headers=H,timeout=30);print('credit status',b.status_code,b.text[:200])
except Exception as e: print('credit check failed',str(e)[:100])
files=[]
for i,p in enumerate(pieces):
    r=requests.post('https://api.fish.audio/v1/tts',headers={**H,'Content-Type':'application/json','model':'s2.1-pro-free'},json={'text':p,'reference_id':os.environ['FISH_VOICE_ID'],'format':'mp3'},timeout=180)
    print('piece',i,len(p),'chars status',r.status_code,len(r.content))
    r.raise_for_status();f=f'/tmp/fp{i}.mp3';open(f,'wb').write(r.content);files.append(f)
open('/tmp/fl.txt','w').write(''.join(f"file '{f}'\n" for f in files))
subprocess.run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i','/tmp/fl.txt','-c','copy',f"audiobook/samples/{cfg['slug']}_fish.mp3"],check=True)
print(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f"audiobook/samples/{cfg['slug']}_fish.mp3"]).decode())
