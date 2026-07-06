import os
import asyncio
import edge_tts
import subprocess
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

story_text = """
كان يا مكان في قديم الزمان، كان فيه ولد شجاع اسمه علي.
علي كان بيحب يساعد الناس وكل يوم عنده مغامرة جديدة.
في يوم لقى قطة صغيرة تايهة، فقرر يساعدها ترجع لبيتها.
ومن هنا بدأت المغامرة...
"""

async def make_audio():
    communicate = edge_tts.Communicate(story_text, "ar-EG-ShakirNeural")
    await communicate.save("story.mp3")

asyncio.run(make_audio())

print("بعمل الفيديو بـ ffmpeg...")
# ده بياخد صورة سودا + ملف الصوت ويطلع فيديو mp4 جاهز لليوتيوب
command = [
    'ffmpeg',
    '-f', 'lavfi', '-i', 'color=c=black:s=1080x1920:d=15', # فيديو اسود 15 ثانية 1080x1920
    '-i', 'story.mp3', # دخل ملف الصوت
    '-c:v', 'libx264', '-tune', 'stillimage', # كودك الفيديو
    '-c:a', 'aac', '-b:a', '192k', # كودك الصوت
    '-pix_fmt', 'yuv420p', '-shortest', # عشان يشتغل على يوتيوب
    'story.mp4'
]
subprocess.run(command, check=True)
print("الفيديو جاهز")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
credentials = flow.run_local_server(port=0)
youtube = build("youtube", "v3", credentials=credentials)

request = youtube.videos().insert(
    part="snippet,status",
    body={
      "snippet": {"title": "قصة قصيرة #shorts", "description": story_text},
      "status": {"privacyStatus": "public"}
    },
    media_body=MediaFileUpload("story.mp4")
)
response = request.execute()
print(f"مبروك الفيديو اترفع: https://youtube.com/watch?v={response['id']}")
