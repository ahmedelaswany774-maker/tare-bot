FROM python:3.11

# سطب ffmpeg + كل حاجة مرة واحدة
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY..

# سطب المكتبات
RUN pip install --no-cache-dir edge-tts google-api-python-client google-auth-oauthlib

# شغل البوت
CMD ["python", "story_youtube_uploader.py"]
