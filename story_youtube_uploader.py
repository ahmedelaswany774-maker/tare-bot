import os
import json
import asyncio
import subprocess
import requests
import edge_tts
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

def generate_story():
    api_key = os.environ["ANTHROPIC_API_KEY"]
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    prompt = (
        "اكتب قصة قصيرة جدًا ومشوقة باللغة العربية الفصحى، "
        "مناسبة لفيديو يوتيوب شورت (30-45 ثانية قراءة)، "
        "لها بداية جذابة ونهاية مؤثرة أو مفاجئة. "
        "اكتب القصة فقط بدون أي مقدمات أو عناوين."
    )
    data = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages", headers=headers, json=data, timeout=60
    )
    resp.raise_for_status()
    result = resp.json()
    return result["content"][0]["text"].strip()


story_text = generate_story()
print("تم توليد القصة:")
print(story_text)

async def make_audio():
    communicate = edge_tts.Communicate(story_text, "ar-EG-ShakirNeural")
    await communicate.save("story.mp3")

asyncio.run(make_audio())

print("بعمل الفيديو...")
command = [
    "ffmpeg",
    "-y",
    "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=10",
    "-i", "story.mp3",
    "-c:v", "libx264", "-tune", "stillimage",
    "-c:a", "aac", "-b:a", "192k",
    "-pix_fmt", "yuv420p", "-shortest",
    "story.mp4",
]
subprocess.run(command, check=True)
print("الفيديو جاهز")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

creds = Credentials.from_authorized_user_info(
    json.loads(os.environ["YT_TOKEN_JSON"]), SCOPES
)

if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())

youtube = build("youtube", "v3", credentials=creds)

video_title = story_text.split("\n")[0][:80] + " #shorts"

request = youtube.videos().insert(
    part="snippet,status",
    body={
        "snippet": {"title": video_title, "description": story_text},
        "status": {"privacyStatus": "public"},
    },
    media_body=MediaFileUpload("story.mp4"),
)
response = request.execute()
print(f"تم رفع الفيديو: https://youtube.com/watch?v={response['id']}")
