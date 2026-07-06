import os
import asyncio
import edge_tts
import subprocess
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

# غير القصة دي براحتك بعدين
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

print("بعمل الفيديو...")
command = [
    'ffmpeg',
    '-f', 'lavfi', '-i', 'color=c=black:s=720x1280:d=10',
    '-i', 'story.mp3',
    '-c:v', 'libx264', '-tune', 'stillimage',
    '-c:a', 'aac', '-b:a', '192k',
    '-pix_fmt', 'yuv420p', '-shortest',
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
