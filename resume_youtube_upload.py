import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

VIDEO_PATH = Path(os.getenv("VIDEO_PATH", "story.mp4"))
STATE_PATH = Path(os.getenv("UPLOAD_STATE_PATH", "upload_state.json"))
METADATA_PATH = Path(os.getenv("METADATA_PATH", "story_metadata.json"))
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def load_metadata():
    if METADATA_PATH.exists():
        try:
            data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
            return {
                "title": str(data.get("title") or "قصة مشوقة جديدة")[:100],
                "description": str(data.get("description") or "قصة عربية مشوقة."),
                "tags": data.get("tags") or ["قصص", "قصة", "قصص_عربية", "story"],
            }
        except Exception as exc:
            print(f"⚠️ تعذر قراءة metadata: {exc}")
    return {
        "title": "قصة مشوقة جديدة",
        "description": "قصة عربية مشوقة.",
        "tags": ["قصص", "قصة", "قصص_عربية", "story"],
    }


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_credentials():
    raw = os.environ.get("YT_TOKEN_JSON")
    if not raw:
        raise RuntimeError("YT_TOKEN_JSON غير موجود في GitHub Actions Secrets")
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise RuntimeError(
                "فشل تحديث YouTube OAuth. يجب إنشاء OAuth client جديد وإعادة إصدار token.json ثم تحديث YT_TOKEN_JSON. "
                f"التفاصيل: {exc}"
            ) from exc
    if not creds.valid:
        raise RuntimeError("YouTube credentials غير صالحة أو منتهية")
    return creds


def upload():
    if not VIDEO_PATH.exists() or VIDEO_PATH.stat().st_size == 0:
        raise FileNotFoundError(f"الفيديو غير موجود: {VIDEO_PATH}")

    state = load_state()
    existing_video_id = state.get("youtube_video_id")
    if existing_video_id:
        print(f"✅ الفيديو مسجل بالفعل كمرفوع: {existing_video_id}")
        return existing_video_id

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    meta = load_metadata()
    description = f"{meta['description']}\n\n#قصص #قصة #قصص_عربية #story"

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": meta["title"],
                "description": description,
                "tags": meta["tags"],
                "categoryId": "24",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=MediaFileUpload(str(VIDEO_PATH), resumable=True),
    )

    response = request.execute()
    video_id = response["id"]
    state.update({"status": "uploaded", "youtube_video_id": video_id, "video": str(VIDEO_PATH)})
    save_state(state)
    print(f"✅ تم رفع الفيديو بنجاح: https://youtube.com/watch?v={video_id}")
    return video_id


if __name__ == "__main__":
    try:
        upload()
    except HttpError as exc:
        print(f"❌ YouTube API error: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"❌ {exc}")
        sys.exit(1)
