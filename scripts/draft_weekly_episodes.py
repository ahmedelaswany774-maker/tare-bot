import json
import os
import re
import time
from pathlib import Path
import requests

MANIFEST = Path("content/series/real_stories.json")
OUT_DIR = Path("content/drafts/verified_real")
API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MIN_WORDS = int(os.getenv("MIN_SCRIPT_WORDS", "2400"))
TARGET_WORDS = int(os.getenv("STORY_TARGET_WORDS", "3200"))
MAX_API_RETRIES = int(os.getenv("MAX_API_RETRIES", "4"))

class GeminiDailyQuotaExceeded(RuntimeError):
    """The Gemini free-tier daily request quota is exhausted; retrying cannot help."""

def word_count(text):
    return len(re.findall(r"\S+", text))

def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    payload = {"contents":[{"parts":[{"text":prompt}]}],
               "generationConfig":{"temperature":0.65,"topP":0.9,"maxOutputTokens":12288}}
    last_error = None
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            response = requests.post(url, json=payload, timeout=300)
            if response.status_code == 429:
                detail = response.text[:2000]
                lowered = detail.lower()
                if ("generate_content_free_tier_requests" in lowered
                        or "per day" in lowered
                        or "quota exceeded" in lowered):
                    raise GeminiDailyQuotaExceeded(
                        f"Gemini daily quota exhausted for {MODEL}; stop this run and resume after quota reset. "
                        f"API response: {detail[:500]}"
                    )
            if response.status_code == 429 or response.status_code in (500, 502, 503, 504):
                retry_after = response.headers.get("Retry-After")
                try:
                    wait_seconds = min(60, max(5, float(retry_after))) if retry_after else min(60, 10 * attempt)
                except ValueError:
                    wait_seconds = min(60, 10 * attempt)
                last_error = f"temporary Gemini status {response.status_code}: {response.text[:500]}"
                if attempt < MAX_API_RETRIES:
                    print(f"Gemini temporary error; retry {attempt}/{MAX_API_RETRIES} after {wait_seconds:.0f}s", flush=True)
                    time.sleep(wait_seconds)
                    continue
                break
            response.raise_for_status()
            body = response.json()
            candidates = body.get("candidates") or []
            if not candidates:
                raise RuntimeError(f"Gemini returned no candidates: {json.dumps(body, ensure_ascii=False)[:1000]}")
            return candidates[0]["content"]["parts"][0]["text"].strip()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError, KeyError, ValueError, RuntimeError) as exc:
            last_error = str(exc)
            if attempt == MAX_API_RETRIES:
                break
            wait_seconds = min(60, 10 * attempt)
            print(f"Gemini request failed; retry {attempt}/{MAX_API_RETRIES} after {wait_seconds}s: {last_error[:250]}", flush=True)
            time.sleep(wait_seconds)
    raise RuntimeError(f"Gemini generation failed after {MAX_API_RETRIES} attempts: {last_error}")

def build_prompt(episode):
    facts = "\n".join(f"- {fact}" for fact in episode.get("verified_facts", []))
    sources = "\n".join(f"- {s.get('title')} | {s.get('publisher')} | {s.get('url')}" for s in episode.get("sources", []))
    return f"""
أنت كاتب سيناريو وثائقي اجتماعي لقناة مصرية اسمها «قصص واقعيه».
اكتب السيناريو الكامل للحلقة رقم {episode['episode_number']} بعنوان: {episode['title']}.
الموضوع: {episode['topic']}
الافتتاحية: {episode.get('opening_hook','')}

الوقائع المتاحة فقط:
{facts}

المصادر المتاحة:
{sources}

قواعد إلزامية:
1. هذه قصة واقعية وليست دراما خيالية. لا تخترع حوارًا أو مشهدًا أو شخصية أو حدثًا أو دافعًا أو تاريخًا أو رقمًا أو نتيجة.
2. لا تملأ الفراغات بمواقف متخيلة، ولا تكتب مشاهد تمثيلية بصيغة حدثت بالفعل.
3. انسب المعلومات إلى التقرير المنشور، ووضح عندما تكون التفاصيل غير متاحة أو غير مؤكدة.
4. إذا كانت الوقائع المنشورة قليلة، وسّع الحلقة بتحليل اجتماعي عام واضح أنه تعليق، لا بإضافة وقائع عن صاحبة القصة.
5. استخدم اللهجة المصرية البيضاء، واحمِ خصوصية الأشخاص.
6. لا تنحرف عن موضوع الحلقة ولا تضف حبكات جانبية أو موضوعات رياضية أو ألغاز أو قصص نجاة أو خيال.
7. لا تقدم نصائح قانونية أو طبية. في موضوع الميراث اعرض القضية وحدود الحكم فقط.
8. لا تنسخ نص المصدر حرفيًا. اكتب صياغة أصلية.
9. اكتب سردًا وثائقيًا طويلًا بافتتاحية قوية وتمهيد وتسلسل الوقائع وسياق اجتماعي وخاتمة.
10. الطول المستهدف نحو {TARGET_WORDS} كلمة عربية، دون حشو أو تكرار.
11. أخرج متن السرد فقط، دون JSON أو تعليمات مونتاج.
""".strip()

def extract_saved_text(path):
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"# النص الكامل\s*(.*?)\s*# ملاحظات المونتاج", raw, re.S)
    return match.group(1).strip() if match else ""

def save_checkpoint(episode, path, text):
    number = int(episode["episode_number"])
    count = word_count(text)
    document = (
        f"# الحلقة {number}: {episode['title']}\n\n"
        f"> مسودة وثائقية محفوظة تلقائيًا. عدد الكلمات الحالي: {count}. "
        f"لا تُنشر قبل استكمال المراجعة التحريرية والتحقق من المصادر.\n\n"
        f"# النص الكامل\n\n{text.strip()}\n\n"
        f"# ملاحظات المونتاج\n\n"
        "- استخدم صورًا أصلية أو مرخصة، ولا تعرض مشاهد تمثيلية على أنها لقطات حقيقية.\n"
        "- أظهر المصادر في الوصف، وراجع كل اسم ورقم وتاريخ قبل التسجيل.\n"
    )
    path.write_text(document, encoding="utf-8")
    episode["script_path"] = path.as_posix()
    episode["draft_status"] = ("written_pending_editorial_and_source_review" if count >= MIN_WORDS
                               else "incomplete_below_minimum_pending_continuation")
    episode["draft_word_count"] = count
    return count

def main():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    episodes = [e for e in data.get("episodes", [])
                if 38 <= int(e.get("episode_number", 0)) <= 65
                and e.get("content_type", data.get("content_type")) == "verified_real_story"]
    if len(episodes) != 28:
        raise SystemExit(f"Expected 28 episodes (38-65), found {len(episodes)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for episode in episodes:
        number = int(episode["episode_number"])
        path = OUT_DIR / f"episode-{number:02d}.md"
        text = extract_saved_text(path)
        count = word_count(text)
        if count >= MIN_WORDS:
            episode["script_path"] = path.as_posix()
            episode["draft_status"] = "written_pending_editorial_and_source_review"
            episode["draft_word_count"] = count
            print(f"Skipping completed episode {number}: {count} words already checkpointed", flush=True)
            continue
        try:
            if text:
                print(f"Resuming episode {number} from saved checkpoint: {count} words", flush=True)
            else:
                print(f"Generating episode {number}: {episode['title']}", flush=True)
                text = call_gemini(build_prompt(episode))
                count = save_checkpoint(episode, path, text)
                MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"Initial checkpoint saved for episode {number}: {count} words", flush=True)

            for attempt in range(1, int(os.getenv("MAX_CONTINUATIONS", "4")) + 1):
                if count >= MIN_WORDS:
                    break
                print(f"Episode {number}: {count} words; continuation {attempt}", flush=True)
                continuation_prompt = (
                    f"استكمل النص التالي فقط دون تكرار أو إعادة المقدمة. المطلوب الوصول إلى {TARGET_WORDS} كلمة إجمالًا. "
                    f"لا تختلق وقائع أو حوارًا أو مشاهد أو أشخاصًا أو أرقامًا. إذا انتهت الوقائع المنشورة، أضف تحليلًا "
                    f"اجتماعيًا عامًا واضحًا أنه تعليق، ومرتبطًا مباشرة بموضوع الحلقة. عنوان الحلقة: {episode['title']}\n"
                    f"النص الحالي:\n{text[-6000:]}"
                )
                addition = call_gemini(continuation_prompt)
                if not addition:
                    break
                text = text.rstrip() + "\n\n" + addition.strip()
                count = save_checkpoint(episode, path, text)
                MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"Checkpoint saved for episode {number}: {count} words", flush=True)
        except GeminiDailyQuotaExceeded as exc:
            count = save_checkpoint(episode, path, text)
            episode["draft_status"] = "deferred_gemini_daily_quota_exhausted"
            MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Gemini daily quota exhausted at episode {number}; checkpoint preserved ({count} words). "
                  f"Stopping this run without spending more requests: {exc}", flush=True)
            break
        except RuntimeError as exc:
            count = save_checkpoint(episode, path, text)
            episode["draft_status"] = "deferred_gemini_error_pending_continuation"
            MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Episode {number} deferred after {MAX_API_RETRIES} Gemini attempts; checkpoint preserved ({count} words): {exc}", flush=True)
            continue

        count = save_checkpoint(episode, path, text)
        MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {path} ({count} words); {episode['draft_status']}", flush=True)
        time.sleep(5)
        print(f"Single completed-episode run: processed episode {number}; remaining episodes will be handled by later scheduled runs.", flush=True)
        break
    completed = sum(1 for e in episodes if int(e.get("draft_word_count", 0)) >= MIN_WORDS)
    print(f"Batch checkpointed: {completed}/28 scripts meet the minimum. No publishing.", flush=True)

if __name__ == "__main__":
    main()
