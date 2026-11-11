#!/usr/bin/env python3
"""Publish one validated Kombo City Short to the authorized YouTube channel."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def main() -> int:
    video_path = Path(os.environ["VIDEO_PATH"])
    metadata_path = Path(os.environ["METADATA_PATH"])
    token_raw = os.getenv("YT_TOKEN_JSON", "").strip()
    if not token_raw:
        raise RuntimeError(
            "YT_TOKEN_JSON is missing. Add the Google OAuth token JSON for the رواة الواقع channel "
            "to GitHub Actions repository secrets."
        )
    if not video_path.is_file() or not metadata_path.is_file():
        raise RuntimeError("Generated MP4 or metadata JSON is missing.")

    token_info = json.loads(token_raw)
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = Credentials.from_authorized_user_info(token_info, scopes=scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("YouTube OAuth credentials are invalid or expired; refresh authorization.")

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    channel_response = youtube.channels().list(part="snippet", mine=True, maxResults=1).execute()
    channels = channel_response.get("items", [])
    if not channels:
        raise RuntimeError("OAuth token has no accessible YouTube channel.")
    channel = channels[0]
    channel_title = channel.get("snippet", {}).get("title", "")
    custom_url = channel.get("snippet", {}).get("customUrl", "")
    expected = os.getenv("YOUTUBE_EXPECTED_HANDLE", "@RowatAlwaqe").lstrip("@").casefold()
    actual = custom_url.lstrip("@").casefold()
    print(f"YouTube OAuth channel: {channel_title} ({custom_url or channel.get('id', 'unknown handle')})")
    if actual and actual != expected:
        raise RuntimeError(
            f"Safety stop: OAuth token belongs to @{custom_url.lstrip('@')}, "
            f"not the requested @{expected}. No video was uploaded."
        )
    if not actual:
        raise RuntimeError(
            "Safety stop: YouTube API did not return the channel handle, so channel identity "
            "could not be verified. No video was uploaded."
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    title = str(metadata.get("title") or "").strip()[:100]
    description = str(metadata.get("caption") or "").strip()[:5000]
    if not title or not description:
        raise RuntimeError("YouTube title or description is empty.")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "27",
            "tags": ["رواة الواقع", "كومبو سيتي", "تعليم", "معلومات تقنية", "Shorts"],
        },
        "status": {"privacyStatus": "public"},
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"YouTube upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube API did not return a video ID after upload.")
    result = {
        "video_id": video_id,
        "url": f"https://www.youtube.com/shorts/{video_id}",
        "channel_title": channel_title,
        "channel_handle": custom_url,
        "privacy_status": "public",
        "title": title,
    }
    receipt_path = video_path.with_suffix(".youtube.json")
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("YOUTUBE_PUBLISHED=" + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"YouTube publish error: {exc}", file=sys.stderr)
        raise SystemExit(1)
