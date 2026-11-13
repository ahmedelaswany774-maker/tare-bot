import argparse
import json
from .memory import StoryMemory

def main():
    parser = argparse.ArgumentParser(description="Hakewina Agent Engine")
    parser.add_argument("--db", default="content/memory/hakewina.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("status")
    add = commands.add_parser("add-idea")
    add.add_argument("--title", required=True)
    add.add_argument("--topic", default="")
    add.add_argument("--angle", default="")
    args = parser.parse_args()
    memory = StoryMemory(args.db)
    if args.command == "init":
        print(json.dumps({"ok": True, "database": args.db}, ensure_ascii=False))
    elif args.command == "status":
        print(json.dumps(memory.list_stories(), ensure_ascii=False, indent=2))
    else:
        result = memory.add_story(args.title, args.topic, args.angle)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["created"] else 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
