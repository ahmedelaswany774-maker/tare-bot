# Kombo City Factory داخل Tare Bot

مصنع فيديوهات تعليمية قصيرة مستقل داخل مستودع tare-bot، ويستخدم نفس أسرار Fish Audio وصوتك المستنسخ المعرّف في المشروع.

- مدة الفيديو: 45 ثانية، عمودي 1080×1920، 30fps.
- التعليق الصوتي: Fish Audio باستخدام FISH_VOICE_ID نفسه المستخدم في Tare Bot.
- لا يوجد fallback إلى Edge TTS؛ إذا فشل Fish Audio يتوقف التشغيل.
- بنك 30 فكرة وسجل منع التكرار محفوظان داخل هذا المجلد.
- لا يرفع هذا المسار الفيديو إلى YouTube؛ يحفظ MP4 كـ Artifact ويعمل commit للنتيجة.

## Secrets المطلوبة
يستخدم الأسرار الموجودة مسبقًا في Tare Bot:
- FISH_API_KEY
- FISH_VOICE_ID
- GEMINI_API_KEY

لا تضع أي مفتاح داخل ملفات الريبو ولا ترسله في المحادثة.

## التشغيل
GitHub → Actions → Kombo City Factory → Run workflow.
الجدولة اليومية مستقلة عن Story Bot.
