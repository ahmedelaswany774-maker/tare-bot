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


def load_token_info(raw: str) -> dict:
    # Accept either the JSON body copied from OAuth Playground or its complete
    # HTTP response (status line + headers + JSON body). Never log token content.
    candidate = raw.strip()
    if candidate.startswith("HTTP/"):
        separator = "\r\n\r\n"
        if separator in candidate:
            candidate = candidate.split(separator, 1)[1].strip()
        elif "\n\n" in candidate:
            candidate = candidate.split("\n\n", 1)[1].strip()
    try:
        info = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "YT_TOKEN_JSON is not valid OAuth JSON. In OAuth Playground Step 2, copy the "
            "complete JSON response body (including its opening { and closing }), not only "
            "the access token. Do not include Markdown fences or explanatory text."
        ) from exc
    if not isinstance(info, dict):
        raise RuntimeError("YT_TOKEN_JSON must be a JSON object.")

    # OAuth Playground returns access_token; google-auth's user-credentials
    # format expects the same value under the key 'token'.
    if not info.get("token") and info.get("access_token"):
        info["token"] = info["access_token"]

    # Keep compatibility with a complete authorized-user JSON, while also
    # supporting the OAuth Playground token response plus separate GitHub secrets.
    info.setdefault("client_id", os.getenv("YT_CLIENT_ID", "").strip())
    info.setdefault("client_secret", os.getenv("YT_CLIENT_SECRET", "").strip())
    info.setdefault("token_uri", "https://oauth2.googleapis.com/token")
    if not info.get("scopes") and info.get("scope"):
        info["scopes"] = info["scope"].split()

    missing = [key for key in ("client_id", "client_secret", "refresh_token") if not info.get(key)]
    if missing:
        raise RuntimeError(
            "OAuth token JSON is missing required fields: " + ", ".join(missing)
            + ". Ensure YT_TOKEN_JSON contains refresh_token and the separate "
            "YT_CLIENT_ID / YT_CLIENT_SECRET secrets belong to the same Web OAuth client."
        )
    if not info.get("token"):
        raise RuntimeError("YT_TOKEN_JSON is missing access_token (or token). Re-authorize the YouTube account.")
    return info


def main() -> int:
    video_path = Path(os.environ["VIDEO_PATH"])
    metadata_path = Path(os.environ["METADATA_PATH"])
    token_raw = os.getenv("YT_TOKEN_JSON", "").strip()
    if not token_raw:
        raise RuntimeError("YT_TOKEN_JSON is missing from GitHub Actions repository secrets.")
    if not video_path.is_file() or not metadata_path.is_file():
        raise RuntimeError("Generated MP4 or metadata JSON is missing.")
    receipt_path = video_path.with_suffix(".youtube.json")
    if receipt_path.exists():
        raise RuntimeError(
            f"Duplicate-upload protection: a YouTube receipt already exists for {video_path.name}; "
            "this file will not be uploaded again."
        )

    token_info = load_token_info(token_raw)
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
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
        "verification": "pending",
        "title": title,
    }
    # Save immediately so a verification failure cannot cause a duplicate upload.
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    verification = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = verification.get("items", [])
    if not items:
        raise RuntimeError(
            f"Upload returned video ID {video_id}, but YouTube did not return it during verification. "
            "Receipt saved; automatic retry is blocked to prevent a duplicate."
        )
    uploaded = items[0]
    uploaded_channel = uploaded.get("snippet", {}).get("channelId")
    uploaded_privacy = uploaded.get("status", {}).get("privacyStatus")
    if uploaded_channel != channel.get("id") or uploaded_privacy != "public":
        raise RuntimeError(
            f"Upload verification mismatch: channel_matches={uploaded_channel == channel.get('id')}, "
            f"privacy={uploaded_privacy}. Receipt saved; manual inspection is required."
        )
    result["verification"] = "confirmed_public_on_expected_channel"
    from datetime import datetime, timezone
    result["verified_at"] = datetime.now(timezone.utc).isoformat()
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("YOUTUBE_PUBLISHED=" + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"YouTube publish error: {exc}", file=sys.stderr)
        raise SystemExit(1)
