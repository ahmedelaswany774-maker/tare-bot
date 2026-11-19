import sqlite3
from pathlib import Path

STAGES = ("idea", "research", "verified", "script", "packaging", "shorts", "production", "published", "rejected")

class StoryMemory:
    def __init__(self, db_path="content/memory/hakewina.sqlite3"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS stories (id INTEGER PRIMARY KEY, title TEXT UNIQUE NOT NULL, topic TEXT DEFAULT '', angle TEXT DEFAULT '', stage TEXT DEFAULT 'idea', evidence_json TEXT DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP)")

    def add_story(self, title, topic="", angle=""):
        with sqlite3.connect(self.db_path) as db:
            try:
                cur = db.execute("INSERT INTO stories(title, topic, angle) VALUES (?, ?, ?)", (title.strip(), topic.strip(), angle.strip()))
                return {"created": True, "id": cur.lastrowid}
            except sqlite3.IntegrityError:
                row = db.execute("SELECT id, title, stage FROM stories WHERE title=?", (title.strip(),)).fetchone()
                return {"created": False, "duplicate": True, "existing": row}

    def list_stories(self):
        with sqlite3.connect(self.db_path) as db:
            return db.execute("SELECT id, title, topic, angle, stage, created_at FROM stories ORDER BY id").fetchall()
