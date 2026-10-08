def main():
    history = load_history()
    print(f"عدد القصص المنشورة سابقًا في السجل: {len(history)}")

    topic_info = pick_topic(history)
    topic = topic_info["topic"]
    print(f"الفئة: {topic_info['category']}")
    print(f"الموضوع: {topic}")

    story_text = generate_story(topic_info)
    word_count = len(story_text.split())
    print(f"عدد كلمات القصة: {word_count}")
    min_words = max(600, STORY_TARGET_WORDS // 3)
    if word_count < min_words:
        raise RuntimeError(
            f"القصة قصيرة جدًا ({word_count} كلمة، المطلوب على الأقل {min_words}) — أوقفنا التشغيل بدل رفع فيديو ناقص"
        )

    meta = generate_metadata(story_text, topic)
    video_title = str(meta.get("title") or topic).strip()
    description = str(meta.get("description") or topic).strip()
    keywords = [str(k).strip() for k in (meta.get("visual_keywords") or []) if str(k).strip()]
    if not keywords:
        keywords = list(DEFAULT_KEYWORDS)
    print(f"العنوان: {video_title}")

    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    story_id = created_at.strftime("%Y%m%d-%H%M%S")

    save_json(
        METADATA_PATH,
