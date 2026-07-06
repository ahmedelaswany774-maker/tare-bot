import os
import asyncio
import random
import textwrap
from datetime import datetime
from openai import OpenAI
import edge_tts
from moviepy import AudioFileClip, ImageClip, CompositeVideoClip, TextClip, CompositeAudioClip, afx
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from supabase import create_client, Client
import yt_dlp

# ====== CONFIG ======
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
VOICE = "ar-EG-ShakirNeural"
VIDEO_W, VIDEO_H = 1080, 1920

openai_client = OpenAI(api_key=OPENAI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def generate_story():
    prompt = """اكتب قصة قصيرة مرعبة باللهجة المصرية عن التار والانتقام في الصعيد.
    لازم تكون 150-200 كلمة. الأسلوب: ساسبنس، غامض، يشد.
    ابدأ بجملة خطف زي: 'الدم ما بينساش...' او 'التار مابيموتش...'
    النهاية تكون صادمة ومفتوحة. ممنوع أي أسماء حقيقية."""
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.1
    )
    return response.choices[0].message.content.strip()

def get_mood(text):
    if "دم" in text or "قتل" in text or "سكين" in text:
        return "dark"
    elif "خوف" in text or "رعب" in text or "صرخة" in text:
        return "suspense"
    else:
        return "calm"

async def make_tts(text, out_path="voice.mp3"):
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(out_path)
    return out_path

def download_music(mood):
    music_files = {
        "dark": ["music/dark.mp3", "music/dark2.mp3"],
        "suspense": ["music/suspense.mp3"],
        "calm": ["music/calm.mp3"]
    }
    
    for f in music_files.get(mood, []):
        if os.path.exists(f):
            return f
    
    print("No local music found, skipping background music")
    return None

def make_video(voice_path, story_text, music_path=None):
    voice = AudioFileClip(voice_path)
    duration = voice.duration
    
    bg = ImageClip(color=(0,0,0), size=(VIDEO_W, VIDEO_H)).with_duration(duration)
    
    wrapped = textwrap.fill(story_text, width=25)
    txt_clip = TextClip(
        wrapped,
        font_size=70,
        color='white',
        font='Noto-Sans-Arabic',
        stroke_color='black',
        stroke_width=3,
        method='caption',
        size=(VIDEO_W-100, None)
    ).with_duration(duration).with_position('center')
    
    video = CompositeVideoClip([bg, txt_clip])
    
    if music_path and os.path.exists(music_path):
        music = AudioFileClip(music_path).with_duration(duration).fx(afx.volumex, 0.1)
        final_audio = CompositeAudioClip([voice, music])
    else:
        final_audio = voice
    
    video = video.with_audio(final_audio)
    out_path = "final_shorts.mp4"
    video.write_videofile(out_path, fps=24, codec="libx264", audio_codec="aac")
    return out_path

def get_youtube_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    
    return build("youtube", "v3", credentials=creds)

def upload_youtube(file_path, title, desc):
    youtube = get_youtube_service()
    
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": ["قصص", "رعب", "تار", "صعيد", "shorts"],
            "categoryId": "24"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }
    
    media = MediaFileUpload(file_path, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    return f"https://youtube.com/shorts/{response['id']}"

def save_to_supabase(story, url):
    data = {
        "story_text": story,
        "youtube_url": url,
        "created_at": datetime.now().isoformat()
    }
    supabase.table("stories").insert(data).execute()

async def main():
    print("بتألف قصة تار...")
    story = generate_story()
    mood = get_mood(story)
    print(f"المود: {mood}")
    
    print("بعمل صوت شاكر المصري...")
    voice_path = await make_tts(story)
    
    print("بحمل موسيقى...")
    music_path = download_music(mood)
    
    print("بدمج الفيديو...")
    video_path = make_video(voice_path, story, music_path)
    
    print("برفع يوتيوب...")
    title = story.split('\n')[0][:90] + " #shorts"
    desc = story[:4500] + "\n\n#قصص #رعب #تار"
    url = upload_youtube(video_path, title, desc)
    print(f"اترفع: {url}")
    
    print("بحفظ في Supabase...")
    save_to_supabase(story, url)
    
    for f in [voice_path, video_path]:
        if os.path.exists(f): os.remove(f)
    
    print("هنام 6 ساعات")
    await asyncio.sleep(6 * 3600)

if __name__ == "__main__":
    while True:
        asyncio.run(main())