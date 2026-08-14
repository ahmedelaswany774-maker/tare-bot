import json
import os
import subprocess
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


METADATA_PATH = Path(os.environ.get("METADATA_PATH", "story_metadata.json"))
STATE_PATH = Path(os.environ.get("STATE_PATH", "upload_state.json"))
SHORT_STATE_PATH = Path("short_state.json")
SOURCE_VIDEO = Path(os.environ.get("SOURCE_VIDEO", "story.mp4"))
SHORT_VIDEO = Path("story_short.mp4")
MAX_SECONDS = int(os.environ.get("SHORT_MAX_SECONDS", "55"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_short() -> None:
    if not SOURCE_VIDEO.exists():
        raise FileNotFoundError(f"missing source video: {SOURCE_VIDEO}")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(SOURCE_VIDEO), "-t", str(MAX_SECONDS),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-movflags", "+faststart", str(SHORT_VIDEO),
        ],
        check=True,
    )


def main() -> None:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    long_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    long_video_id = long_state.get("youtube_video_id")
    if not long_video_id:
        raise ValueError("long video must be uploaded before publishing the Short")

    render_short()
    creds = Credentials.from_authorized_user_info(
        json.loads(os.environ["YT_TOKEN_JSON"]),
        ["https://www.googleapis.com/auth/youtube.upload"],
    )
    creds.refresh(Request())
    youtube = build("youtube", "v3", credentials=creds)

    title = f"{metadata['title']} | الحلقة {metadata['episode_number']} #Shorts"
    description = (
        f"مقطع تشويقي من الحلقة الكاملة: https://www.youtube.com/watch?v={long_video_id}\n\n"
        f"سلسلة: {metadata['series_title']}\n"
        f"المصادر: " + " ".join(source["url"] for source in metadata["sources"])
    )
    response = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": metadata.get("tags", []) + ["Shorts", "قصص واقعية"],
                "categoryId": "24",
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(str(SHORT_VIDEO)),
    ).execute()

    short_video_id = response["id"]
    save_json(
        SHORT_STATE_PATH,
        {
            "status": "uploaded",
            "short_video_id": short_video_id,
            "related_long_video_id": long_video_id,
            "series_id": metadata["series_id"],
            "episode_id": metadata["episode_id"],
            "episode_number": metadata["episode_number"],
            "video": str(SHORT_VIDEO),
        },
    )
    print(f"تم رفع الـShort: https://youtube.com/shorts/{short_video_id}")


if __name__ == "__main__":
    main()
