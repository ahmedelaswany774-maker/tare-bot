import hashlib
import hmac
import os
import sqlite3
from pathlib import Path
from threading import Thread

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
DB_PATH = Path(os.getenv("WEBHOOK_DB", "webhook.sqlite3"))
META_VERIFY_TOKEN = os.environ["META_VERIFY_TOKEN"]
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
WHATSAPP_ACCESS_TOKEN = os.environ["WHATSAPP_ACCESS_TOKEN"]
WHATSAPP_PHONE_NUMBER_ID = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")
GITHUB_DISPATCH_TOKEN = os.environ["GITHUB_DISPATCH_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
GITHUB_REF = os.getenv("GITHUB_REF", "main")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS inbound (message_id TEXT PRIMARY KEY, sender TEXT NOT NULL)")
    conn.commit()
    return conn


def seen(message_id: str, sender: str) -> bool:
    with db() as conn:
        try:
            conn.execute("INSERT INTO inbound(message_id, sender) VALUES (?, ?)", (message_id, sender))
            conn.commit()
            return False
        except sqlite3.IntegrityError:
            return True


def valid_signature(raw: bytes) -> bool:
    if not META_APP_SECRET:
        return True
    supplied = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(META_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def send_text(to: str, body: str) -> None:
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
        json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "text", "text": {"preview_url": False, "body": body[:4096]}},
        timeout=20,
    )
    response.raise_for_status()


def dispatch_story(episode_number: str = "1", tts_backend: str = "edge") -> None:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/story-bot.yml/dispatches"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {GITHUB_DISPATCH_TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        json={"ref": GITHUB_REF, "inputs": {"episode_number": episode_number, "tts_backend": tts_backend, "publish_short": "false"}},
        timeout=20,
    )
    response.raise_for_status()


def process_message(sender: str, message_id: str, text: str) -> None:
    normalized = text.strip().lower()
    if normalized.startswith("أنشئ قصة") or normalized.startswith("انشئ قصة"):
        dispatch_story()
        send_text(sender, "تم استلام الطلب وبدء تجهيز القصة. سأرسل الحالة عند اكتمال الفيديو.")
    elif normalized in {"الحالة", "status"}:
        send_text(sender, "تم استلام طلب الحالة. ستتم إضافة متابعة GitHub في الخطوة التالية.")
    elif normalized in {"نشر", "publish"}:
        send_text(sender, "تم استلام الموافقة. اربط هذا الأمر بـ recover-upload.yml بعد إضافة artifact/run lookup.")
    else:
        send_text(sender, "الأوامر المتاحة: أنشئ قصة، الحالة، نشر")


@app.get("/webhooks/whatsapp")
def verify_webhook():
    if request.args.get("hub.verify_token") != META_VERIFY_TOKEN:
        return "forbidden", 403
    return request.args.get("hub.challenge", ""), 200


@app.post("/webhooks/whatsapp")
def receive_webhook():
    raw = request.get_data(cache=True)
    if not valid_signature(raw):
        return "invalid signature", 403
    payload = request.get_json(silent=True) or {}
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                message_id = message.get("id")
                sender = message.get("from")
                text = (message.get("text") or {}).get("body", "")
                if not message_id or not sender or seen(message_id, sender):
                    continue
                Thread(target=process_message, args=(sender, message_id, text), daemon=True).start()
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
