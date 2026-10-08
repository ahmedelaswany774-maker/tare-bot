import os
import json
import math
import time
import re
import random
import subprocess
import asyncio
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

import edge_tts
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_KEY = os.environ["PEXELS_API_KEY"]
FISH_API_KEY = os.environ.get("FISH_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")
TTS_BACKEND = os.environ.get("TTS_BACKEND", "fish").lower()
VOICE_REFERENCE_PATH = os.environ.get("VOICE_REFERENCE_PATH", "voice_reference.wav")
XTTS_LANGUAGE = os.environ.get("XTTS_LANGUAGE", "ar")
PUBLISH_DELAY_MINUTES = int(os.environ.get("PUBLISH_DELAY_MINUTES", "30"))
