import os
import asyncio
import edge_tts
from moviepy import *
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

# 1. القصة الجاهزة - غيرها براحتك
story_text = """
كان يا مكان في قديم الزمان، كان فيه ولد شجاع اسمه علي.
علي كان بيحب يساعد الناس وكل يوم عنده مغامرة جديدة.
في يوم لقى قطة صغيرة تايهة، فقرر يساعدها ترجع لبيتها.
ومن هنا بدأت المغامرة...
"""

# 2. اعمل الصوت
async def make_audio():
    communicate = edge_tts.Communicate(story_text, "ar-EG-ShakirNeural")
    await communicate.save("story.mp3")

asyncio.run(make_audio())

# 3. اعمل الفيديو
print("بعمل الفيديو...")
audioclip = AudioFileClip("story.mp3")
videoclip = ColorClip(size=(1080,1920), color=(0,0,0), duration=audioclip.duration)
videoclip = videoclip.with_audio(audioclip)  # moviepy الجديد
videoclip.write_videofile("story.mp4", fps=24, codec="libx264")
print("الفيديو جاهز")

# 4. ارفع على يوتيوب
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
credentials = flow.run_local_server(port=0)
youtube = build("youtube", "v3", credentials=credentials)

request = youtube.videos().insert(
    part="snippet,status",
    body={
      "snippet": {
          "title": "قصة قصيرة #shorts",
          "description": story_text,
          "tags": ["قصص", "حكايات", "shorts"]
      },
      "status": {"privacyStatus": "public"}
    },
    media_body=MediaFileUpload("story.mp4")
)
response = request.execute()
print(f"مبروك الفيديو اترفع: https://youtube.com/watch?v={response['id']}")
